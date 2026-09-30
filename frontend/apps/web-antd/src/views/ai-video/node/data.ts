import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { AiVideoNode } from '#/api/ai-video/node';

import { formatDateTime } from '@vben/utils';

export function useNodeGridColumns(): VxeTableGridOptions<AiVideoNode>['columns'] {
  return [
    { field: 'name', minWidth: 150, title: '节点名称' },
    { field: 'code', minWidth: 150, title: '节点编码' },
    {
      field: 'onlineStatus',
      slots: { default: 'onlineStatus' },
      title: '状态',
      width: 100,
    },
    { field: 'agentVersion', title: 'Agent 版本', width: 130 },
    {
      field: 'taskCount',
      title: '关联任务',
      width: 100,
      formatter: ({ cellValue }) => cellValue ?? '未提供',
    },
    {
      field: 'modelCount',
      title: '就绪模型版本',
      width: 115,
      formatter: ({ cellValue }) => cellValue ?? '未提供',
    },
    { field: 'hostName', minWidth: 150, title: '主机名' },
    { field: 'ipAddress', minWidth: 130, title: 'IP 地址' },
    {
      field: 'lastHeartbeatTime',
      minWidth: 170,
      title: '最后心跳',
      formatter: ({ cellValue }) =>
        cellValue ? formatDateTime(cellValue) : '尚未上报',
    },
    {
      field: 'resourceSnapshot',
      minWidth: 300,
      slots: { default: 'resources' },
      title: '资源使用',
    },
    {
      field: 'actions',
      fixed: 'right',
      slots: { default: 'actions' },
      title: '操作',
      width: 260,
    },
  ];
}
