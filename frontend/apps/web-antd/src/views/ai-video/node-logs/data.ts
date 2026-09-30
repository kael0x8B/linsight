import type { VbenFormSchema } from '#/adapter/form';
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { AiVideoNodeLogApi } from '#/api/ai-video/node-log';

import { formatDateTime } from '@vben/utils';

import { getRangePickerDefaultProps } from '#/utils';

export function useLogFormSchema(): VbenFormSchema[] {
  return [
    {
      component: 'InputNumber',
      componentProps: { allowClear: true, min: 1, placeholder: '任务 ID' },
      fieldName: 'taskId',
      label: '任务',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: [
          { label: 'Edge Agent', value: 'EDGE_AGENT' },
          { label: 'AI Runtime', value: 'AI_RUNTIME' },
          { label: '任务', value: 'TASK' },
        ],
      },
      fieldName: 'component',
      label: '组件',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: ['DEBUG', 'INFO', 'WARN', 'ERROR'].map((value) => ({
          label: value,
          value,
        })),
      },
      fieldName: 'level',
      label: '级别',
    },
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
        placeholder: '正文、上下文或诊断 ID',
      },
      fieldName: 'keyword',
      label: '关键字',
    },
    {
      component: 'RangePicker',
      componentProps: { ...getRangePickerDefaultProps(), allowClear: true },
      fieldName: 'loggedAt',
      label: '日志时间',
    },
  ];
}

export function useLogColumns(): VxeTableGridOptions<AiVideoNodeLogApi.Log>['columns'] {
  return [
    {
      field: 'loggedAt',
      minWidth: 180,
      title: '时间',
      formatter: ({ cellValue }) => formatDateTime(cellValue),
    },
    { field: 'level', slots: { default: 'level' }, title: '级别', width: 90 },
    { field: 'component', minWidth: 120, title: '组件' },
    { field: 'taskId', title: '任务 ID', width: 100 },
    { field: 'runId', minWidth: 180, title: 'Run ID' },
    {
      field: 'message',
      minWidth: 420,
      slots: { default: 'message' },
      title: '日志正文',
    },
    { field: 'diagnosticId', minWidth: 180, title: '诊断 ID' },
    {
      field: 'actions',
      fixed: 'right',
      slots: { default: 'actions' },
      title: '操作',
      width: 100,
    },
  ];
}
