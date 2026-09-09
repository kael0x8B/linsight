import type { VbenFormSchema } from '#/adapter/form';
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { AiVideoCameraApi } from '#/api/ai-video/camera';

import { CommonStatusEnum, DICT_TYPE } from '@vben/constants';
import { getDictOptions } from '@vben/hooks';
import { handleTree } from '@vben/utils';

import { z } from '#/adapter/form';
import { getCameraGroupList } from '#/api/ai-video/camera';

async function getGroupTree(includeRoot = false) {
  const groups = await getCameraGroupList();
  if (includeRoot) {
    groups.unshift({
      id: 0,
      name: '未分组',
      parentId: -1,
      sort: 0,
      status: CommonStatusEnum.ENABLE,
    });
  }
  return handleTree(groups, 'id', 'parentId', 'children');
}

export function useCameraFormSchema(): VbenFormSchema[] {
  return [
    {
      fieldName: 'id',
      component: 'Input',
      dependencies: { triggerFields: [''], show: () => false },
    },
    {
      fieldName: 'name',
      label: '摄像头名称',
      component: 'Input',
      componentProps: { maxlength: 100, placeholder: '例如：一号门岗' },
      rules: 'required',
    },
    {
      fieldName: 'code',
      label: '摄像头编码',
      component: 'Input',
      componentProps: {
        maxlength: 64,
        placeholder: '例如：CAM-GATE-001',
      },
      rules: z
        .string()
        .min(1, '摄像头编码不能为空')
        .regex(/^[A-Za-z0-9_-]+$/, '只能包含字母、数字、下划线和连字符'),
    },
    {
      fieldName: 'groupId',
      label: '所属分组',
      component: 'ApiTreeSelect',
      componentProps: {
        api: () => getGroupTree(true),
        childrenField: 'children',
        labelField: 'name',
        placeholder: '请选择分组',
        treeDefaultExpandAll: true,
        valueField: 'id',
      },
      rules: z.number().default(0),
    },
    {
      fieldName: 'protocol',
      label: '接入协议',
      component: 'Select',
      componentProps: {
        options: [
          { label: 'RTSP', value: 'RTSP' },
          { label: 'ONVIF', value: 'ONVIF' },
        ],
        placeholder: '请选择接入协议',
      },
      rules: 'selectRequired',
    },
    {
      fieldName: 'host',
      label: '设备地址',
      component: 'Input',
      componentProps: { maxlength: 255, placeholder: 'IP 或主机名，不含凭据' },
      rules: 'required',
    },
    {
      fieldName: 'port',
      label: '设备端口',
      component: 'InputNumber',
      componentProps: { class: '!w-full', min: 1, max: 65_535 },
      rules: z.number().min(1).max(65_535).default(554),
    },
    {
      fieldName: 'mainStreamUri',
      label: '主码流路径',
      component: 'Input',
      componentProps: {
        maxlength: 4096,
        placeholder: '例如：/Streaming/Channels/101',
      },
      rules: z.string().max(4096).optional(),
    },
    {
      fieldName: 'subStreamUri',
      label: '子码流路径',
      component: 'Input',
      componentProps: {
        maxlength: 4096,
        placeholder: '例如：/Streaming/Channels/102',
      },
      rules: z.string().max(4096).optional(),
    },
    {
      fieldName: 'username',
      label: '访问用户名',
      component: 'Input',
      componentProps: { autocomplete: 'off', maxlength: 512 },
      rules: z.string().max(512).optional(),
    },
    {
      fieldName: 'password',
      label: '访问密码',
      component: 'InputPassword',
      componentProps: { autocomplete: 'new-password', maxlength: 512 },
      rules: z.string().max(512).optional(),
    },
    {
      fieldName: 'status',
      label: '状态',
      component: 'RadioGroup',
      componentProps: {
        buttonStyle: 'solid',
        optionType: 'button',
        options: getDictOptions(DICT_TYPE.COMMON_STATUS, 'number'),
      },
      rules: z.number().default(CommonStatusEnum.ENABLE),
    },
  ];
}

export function useCameraGroupFormSchema(): VbenFormSchema[] {
  return [
    {
      fieldName: 'id',
      component: 'Input',
      dependencies: { triggerFields: [''], show: () => false },
    },
    {
      fieldName: 'parentId',
      label: '上级分组',
      component: 'ApiTreeSelect',
      componentProps: {
        api: async () => {
          const groups = await getCameraGroupList();
          groups.unshift({
            id: 0,
            name: '顶级分组',
            parentId: -1,
            sort: 0,
            status: CommonStatusEnum.ENABLE,
          });
          return handleTree(groups, 'id', 'parentId', 'children');
        },
        childrenField: 'children',
        labelField: 'name',
        placeholder: '请选择上级分组',
        treeDefaultExpandAll: true,
        valueField: 'id',
      },
      rules: z.number().default(0),
    },
    {
      fieldName: 'name',
      label: '分组名称',
      component: 'Input',
      componentProps: { maxlength: 100, placeholder: '请输入分组名称' },
      rules: 'required',
    },
    {
      fieldName: 'sort',
      label: '显示顺序',
      component: 'InputNumber',
      componentProps: { class: '!w-full', min: 0 },
      rules: z.number().min(0).default(0),
    },
    {
      fieldName: 'status',
      label: '状态',
      component: 'RadioGroup',
      componentProps: {
        buttonStyle: 'solid',
        optionType: 'button',
        options: getDictOptions(DICT_TYPE.COMMON_STATUS, 'number'),
      },
      rules: z.number().default(CommonStatusEnum.ENABLE),
    },
  ];
}

export function useCameraGridFormSchema(): VbenFormSchema[] {
  return [
    {
      fieldName: 'name',
      label: '摄像头名称',
      component: 'Input',
      componentProps: { allowClear: true, placeholder: '请输入名称' },
    },
    {
      fieldName: 'code',
      label: '摄像头编码',
      component: 'Input',
      componentProps: { allowClear: true, placeholder: '请输入编码' },
    },
    {
      fieldName: 'protocol',
      label: '接入协议',
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: [
          { label: 'RTSP', value: 'RTSP' },
          { label: 'ONVIF', value: 'ONVIF' },
        ],
        placeholder: '全部协议',
      },
    },
    {
      fieldName: 'onlineStatus',
      label: '在线状态',
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: [
          { label: '未知', value: 0 },
          { label: '在线', value: 1 },
          { label: '离线', value: 2 },
        ],
        placeholder: '全部状态',
      },
    },
  ];
}

export function useCameraGridColumns(): VxeTableGridOptions<AiVideoCameraApi.Camera>['columns'] {
  return [
    { field: 'name', title: '摄像头名称', minWidth: 200, fixed: 'left', align: 'left' },
    { field: 'code', title: '编码', minWidth: 160, align: 'left' },
    { field: 'recognitionCapabilities', title: '识别能力', minWidth: 280, align: 'left', showOverflow: false, slots: { default: 'recognitionCapabilities' } },
    {
      field: 'groupId',
      title: '分组',
      minWidth: 130,
      slots: { default: 'group' },
    },
    { field: 'protocol', title: '协议', width: 90 },
    {
      field: 'onlineStatus',
      title: '在线状态',
      width: 110,
      slots: { default: 'onlineStatus' },
    },
    {
      field: 'maskedStreamEndpoint',
      title: '码流端点（已脱敏）',
      minWidth: 220,
      slots: { default: 'endpoint' },
    },
    {
      field: 'credentialConfigured',
      title: '访问凭据',
      width: 100,
      formatter: ({ cellValue }) => (cellValue ? '已配置' : '未配置'),
    },
    {
      field: 'status',
      title: '启用状态',
      width: 100,
      cellRender: {
        name: 'CellDict',
        props: { type: DICT_TYPE.COMMON_STATUS },
      },
    },
    {
      field: 'lastCheckTime',
      title: '最近检测',
      minWidth: 170,
      formatter: 'formatDateTime',
    },
    {
      title: '操作',
      width: 180,
      fixed: 'right',
      slots: { default: 'actions' },
    },
  ];
}
