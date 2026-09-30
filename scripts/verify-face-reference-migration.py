#!/usr/bin/env python3
"""Verify re-extraction against real MySQL in a disposable schema; never alter application data."""
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / 'backend/sql/mysql/migrations/ai-video'


def main():
    schema = 'linsight_face_reference_test_' + uuid4().hex
    container = os.environ.get('LINSIGHT_MYSQL_CONTAINER', 'linsight-mysql')
    env = {**os.environ, 'MYSQL_PWD': os.environ.get('MYSQL_ROOT_PASSWORD', 'linsight_dev')}

    def sql(statement, database=None, duplicate=False):
        command = ['docker', 'exec', '-i', '-e', 'MYSQL_PWD', container,
                   'mysql', '-uroot', '--batch', '--skip-column-names']
        if database:
            command.append(database)
        result = subprocess.run(command, input=statement, text=True, env=env, capture_output=True)
        if duplicate:
            assert result.returncode != 0 and 'Duplicate entry' in result.stderr, result.stderr
        elif result.returncode:
            raise RuntimeError(result.stderr)
        return result.stdout.strip()

    original = (MIGRATIONS / 'V202609081300__add_entry_access_workflow.sql').read_text()
    original = original.split('CREATE TABLE IF NOT EXISTS ai_entry_access')[0]
    migration = (MIGRATIONS / 'V202609091800__face_reference_extraction_history.sql').read_text()

    def reference(command, tenant=1):
        return f"""INSERT INTO ai_face_reference
        (entry_id, library_id, model_version_id, object_ref, sha256,
         validation_status, validation_command_id, valid_until, tenant_id)
        VALUES (8, 1, 131, 'fixture-photo', REPEAT('a',64), 'READY',
                '{command}', '2099-01-01', {tenant});"""

    sql(f'CREATE DATABASE `{schema}`;')
    try:
        sql(original, schema)
        sql(migration, schema)
        sql(migration, schema)
        sql('DROP TABLE ai_face_reference;', schema)
        sql(original, schema)
        sql(reference('original-command'), schema)
        baseline = sql('SELECT * FROM ai_face_reference;', schema)
        sql(reference('new-command'), schema, duplicate=True)
        sql(migration, schema)
        sql(migration, schema)
        assert sql('SELECT * FROM ai_face_reference;', schema) == baseline
        sql(reference('new-command'), schema)
        sql(reference('new-command'), schema, duplicate=True)
        sql(reference('new-command', tenant=2), schema)
        assert sql('SELECT COUNT(*) FROM ai_face_reference;', schema) == '3'
        # A logically deleted historical record must not prevent another authorized extraction.
        sql("UPDATE ai_face_reference SET deleted=1 WHERE validation_command_id='original-command';", schema)
        sql(reference('renewed-command'), schema)
        assert sql('SELECT COUNT(*) FROM ai_face_reference WHERE tenant_id=1 AND entry_id=8;', schema) == '3'
        indexes = sql("SHOW INDEX FROM ai_face_reference;", schema)
        assert 'uk_face_reference_entry' not in indexes
        assert 'uk_face_reference_command' in indexes and 'idx_face_reference_entry' in indexes
        print(json.dumps({'cleanAndRepeatedMigration': True, 'oldConflictReproduced': True,
                          'historyPreserved': True, 'reExtractionAccepted': True,
                          'duplicateCommandRejected': True, 'tenantIsolation': True,
                          'deletedHistoryPreserved': True}))
    finally:
        sql(f'DROP DATABASE `{schema}`;')


if __name__ == '__main__':
    main()
