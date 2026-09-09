# Offline pip seed

`pip-25.3-py3-none-any.whl` is the unmodified universal wheel published by PyPA
on [PyPI](https://pypi.org/project/pip/25.3/). Its MIT license and bundled-library
licenses are included in the wheel's `pip-25.3.dist-info/licenses/` directory.

Source: https://files.pythonhosted.org/packages/44/3c/d717024885424591d5376220b5e836c2d5293ce2011523c9de23ff7bf068/pip-25.3-py3-none-any.whl

SHA256: `9655943313a94722b7774661c21049070f6bbb0a1516bf02f7c8d5d9201514cd`

The deployment archive carries this asset even without a full offline wheelhouse.
`environment.py` verifies it before use and seeds only the application venv,
without network access, system package writes, or unholding vendor packages.
Version updates must update the wheel and the pinned hash together and rerun the
offline bootstrap tests. Do not replace this asset with a mutable get-pip script.
