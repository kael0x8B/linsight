import type { VbenFormSchema } from '#/adapter/form';
import type { VxeTableGridOptions } from '#/adapter/vxe-table';

import { z } from '#/adapter/form';

const sourceOptions = [
  { label: '预置', value: 'PRESET' },
  { label: '自定义', value: 'CUSTOM' },
];

const formatOptions = [
  { label: 'ONNX', value: 'ONNX' },
  { label: 'TorchScript', value: 'TORCHSCRIPT' },
  { label: 'PyTorch', value: 'PYTORCH' },
  { label: 'TensorRT', value: 'TENSORRT' },
  { label: 'RKNN', value: 'RKNN' },
  { label: '归档包', value: 'ARCHIVE' },
];

const publishOptions = [
  { label: '草稿', value: 'DRAFT' },
  { label: '已发布', value: 'PUBLISHED' },
  { label: '已替代', value: 'SUPERSEDED' },
];

export function useModelGridFormSchema(): VbenFormSchema[] {
  return [
    {
      component: 'Input',
      componentProps: { allowClear: true, placeholder: '请输入模型名称' },
      fieldName: 'name',
      label: '模型名称',
    },
    {
      component: 'Input',
      componentProps: { allowClear: true, placeholder: '请输入稳定编码' },
      fieldName: 'code',
      label: '模型编码',
    },
    {
      component: 'Select',
      componentProps: { allowClear: true, options: sourceOptions },
      fieldName: 'sourceType',
      label: '来源',
    },
    {
      component: 'Select',
      componentProps: { allowClear: true, options: formatOptions },
      fieldName: 'artifactFormat',
      label: '格式',
    },
    {
      component: 'Select',
      componentProps: { allowClear: true, options: publishOptions },
      fieldName: 'publishStatus',
      label: '发布状态',
    },
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
      defaultValue: 0,
      label: '资产状态',
    },
  ];
}

export function useModelGridColumns(): VxeTableGridOptions['columns'] {
  return [
    {
      field: 'name',
      fixed: 'left',
      width: 230,
      slots: { default: 'name' },
      title: '模型',
    },
    {
      field: 'sourceType',
      minWidth: 90,
      slots: { default: 'sourceType' },
      title: '来源',
    },
    {
      field: 'latestVersion',
      width: 230,
      slots: { default: 'latestVersion' },
      title: '默认版本 / 最新草稿',
    },
    {
      field: 'outputLabels',
      minWidth: 210,
      slots: { default: 'outputLabels' },
      title: '识别类别',
    },
    {
      field: 'capabilities',
      minWidth: 250,
      slots: { default: 'capabilities' },
      title: '关联算法',
    },
    { field: 'artifactFormat', minWidth: 110, title: '格式' },
    {
      field: 'artifactSize',
      formatter: 'formatFileSize',
      minWidth: 110,
      title: '大小',
    },
    { field: 'licenseSpdx', minWidth: 160, title: '许可证' },
    {
      field: 'publishStatus',
      minWidth: 110,
      slots: { default: 'publishStatus' },
      title: '发布状态',
    },
    {
      field: 'readyNodeCount',
      minWidth: 120,
      slots: { default: 'deployments' },
      title: '部署节点',
    },
    {
      field: 'status',
      minWidth: 90,
      slots: { default: 'status' },
      title: '资产状态',
    },
    {
      fixed: 'right',
      slots: { default: 'actions' },
      title: '操作',
      width: 130,
    },
  ];
}

export function useModelFormSchema(): VbenFormSchema[] {
  return [
    {
      component: 'Input',
      componentProps: { maxlength: 100 },
      fieldName: 'name',
      label: '模型名称',
      rules: z.string().trim().min(1, '请输入模型名称').max(100),
    },
    {
      component: 'Input',
      componentProps: { maxlength: 64, placeholder: '小写字母、数字和连字符' },
      fieldName: 'code',
      label: '稳定编码',
      rules: z
        .string()
        .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/, '请输入小写字母、数字和连字符')
        .max(64),
    },
    {
      component: 'Select',
      componentProps: { options: sourceOptions },
      fieldName: 'sourceType',
      label: '来源',
      rules: z.enum(['CUSTOM', 'PRESET']).default('CUSTOM'),
    },
    {
      component: 'Textarea',
      componentProps: { maxlength: 500, rows: 4, showCount: true },
      fieldName: 'description',
      label: '说明',
      rules: z.string().max(500).optional(),
    },
  ];
}

export function useVersionGridColumns(): VxeTableGridOptions['columns'] {
  return [
    {
      field: 'version',
      fixed: 'left',
      minWidth: 120,
      slots: { default: 'version' },
      title: '版本',
    },
    { field: 'artifactFormat', minWidth: 110, title: '格式' },
    {
      field: 'artifactSize',
      formatter: 'formatFileSize',
      minWidth: 110,
      title: '大小',
    },
    { field: 'licenseSpdx', minWidth: 130, title: '许可证' },
    {
      field: 'validationStatus',
      minWidth: 110,
      slots: { default: 'validationStatus' },
      title: '格式校验',
    },
    {
      field: 'publishStatus',
      minWidth: 110,
      slots: { default: 'publishStatus' },
      title: '发布状态',
    },
    {
      field: 'sha256',
      minWidth: 220,
      slots: { default: 'sha256' },
      title: 'SHA256',
    },
    {
      fixed: 'right',
      slots: { default: 'actions' },
      title: '操作',
      width: 130,
    },
  ];
}

export function useDeploymentGridColumns(): VxeTableGridOptions['columns'] {
  return [
    { field: 'nodeId', minWidth: 100, title: '节点 ID' },
    {
      field: 'actualStatus',
      minWidth: 120,
      slots: { default: 'actualStatus' },
      title: '实际状态',
    },
    { field: 'backend', minWidth: 120, title: '推理后端' },
    { field: 'device', minWidth: 120, title: '设备' },
    { field: 'configVersion', minWidth: 110, title: '配置版本' },
    { field: 'diagnosticId', minWidth: 180, title: '诊断 ID' },
    {
      field: 'readyTime',
      minWidth: 180,
      formatter: 'formatDateTime',
      title: '就绪时间',
    },
  ];
}

export function useTestGridColumns(): VxeTableGridOptions['columns'] {
  return [
    { field: 'imageName', minWidth: 160, title: '测试图片' },
    {
      field: 'status',
      minWidth: 110,
      slots: { default: 'testStatus' },
      title: '状态',
    },
    { field: 'backend', minWidth: 120, title: '推理后端' },
    { field: 'inferenceMillis', minWidth: 110, title: '推理耗时(ms)' },
    { field: 'diagnosticId', minWidth: 180, title: '诊断 ID' },
    {
      field: 'createTime',
      minWidth: 180,
      formatter: 'formatDateTime',
      title: '创建时间',
    },
  ];
}
