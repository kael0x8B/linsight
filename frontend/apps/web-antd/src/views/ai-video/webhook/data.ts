import type { VbenFormSchema } from '#/adapter/form';
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { AiVideoWebhookApi } from '#/api/ai-video/webhook';

export function endpointSearchSchema(): VbenFormSchema[] {
  return [
    { component: 'Input', fieldName: 'name', label: '端点名称' },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: [
          { label: '启用', value: 0 },
          { label: '停用', value: 1 },
        ],
      },
      fieldName: 'status',
      label: '状态',
    },
  ];
}

export function endpointColumns(): VxeTableGridOptions<AiVideoWebhookApi.Endpoint>['columns'] {
  return [
    { field: 'name', minWidth: 150, title: '端点名称' },
    { field: 'url', minWidth: 280, showOverflow: true, title: 'HTTPS 地址' },
    { field: 'status', slots: { default: 'status' }, title: '状态', width: 90 },
    {
      field: 'scope',
      minWidth: 220,
      slots: { default: 'scope' },
      title: '订阅范围',
    },
    {
      field: 'successRate',
      slots: { default: 'successRate' },
      title: '成功率',
      width: 100,
    },
    { field: 'lastSuccessTime', minWidth: 165, title: '最近成功' },
    { field: 'lastFailureTime', minWidth: 165, title: '最近失败' },
    {
      field: 'actions',
      fixed: 'right',
      slots: { default: 'actions' },
      title: '操作',
      width: 280,
    },
  ];
}

export function deliverySearchSchema(): VbenFormSchema[] {
  return [
    {
      component: 'InputNumber',
      componentProps: { min: 1, placeholder: '端点 ID' },
      fieldName: 'endpointId',
      label: '端点 ID',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: ['PENDING', 'RETRY', 'SUCCEEDED', 'DEAD'].map((value) => ({
          label: value,
          value,
        })),
      },
      fieldName: 'status',
      label: '状态',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: [
          { label: '真实事件', value: false },
          { label: '模拟测试', value: true },
        ],
      },
      fieldName: 'isTest',
      label: '消息来源',
    },
  ];
}

export function deliveryColumns(): VxeTableGridOptions<AiVideoWebhookApi.Delivery>['columns'] {
  return [
    { field: 'id', title: '投递 ID', width: 100 },
    { field: 'endpointId', title: '端点 ID', width: 100 },
    { field: 'eventType', minWidth: 150, title: '事件类型' },
    { field: 'severity', title: '等级', width: 90 },
    {
      field: 'status',
      slots: { default: 'status' },
      title: '状态',
      width: 110,
    },
    { field: 'attempts', title: '尝试次数', width: 100 },
    { field: 'responseStatus', title: 'HTTP', width: 90 },
    {
      field: 'durationMs',
      slots: { default: 'duration' },
      title: '耗时',
      width: 100,
    },
    { field: 'nextAttemptTime', minWidth: 165, title: '下次重试' },
    { field: 'createTime', minWidth: 165, title: '创建时间' },
    {
      field: 'actions',
      fixed: 'right',
      slots: { default: 'actions' },
      title: '操作',
      width: 140,
    },
  ];
}
