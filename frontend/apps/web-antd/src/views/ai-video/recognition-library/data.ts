import type { VbenFormSchema } from '#/adapter/form';
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { AiVideoRecognitionLibraryApi } from '#/api/ai-video/recognition-library';

export function librarySearchSchema(): VbenFormSchema[] {
  return [
    { component: 'Input', fieldName: 'name', label: '库名称' },
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

export function libraryColumns(): VxeTableGridOptions<AiVideoRecognitionLibraryApi.Library>['columns'] {
  return [
    { field: 'name', minWidth: 170, title: '参考库' },
    { field: 'code', minWidth: 170, title: '稳定编码' },
    { field: 'entryCount', title: '条目数', width: 80 },
    { field: 'status', slots: { default: 'status' }, title: '状态', width: 80 },
    {
      field: 'actions',
      fixed: 'right',
      slots: { default: 'actions' },
      title: '操作',
      width: 190,
    },
  ];
}

export function entrySearchSchema(): VbenFormSchema[] {
  return [
    { component: 'Input', fieldName: 'name', label: '名称/编码' },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: ['PENDING', 'READY', 'FAILED'].map((value) => ({
          label: value,
          value,
        })),
      },
      fieldName: 'featureStatus',
      label: '特征状态',
    },
  ];
}

export function entryColumns(
  type: AiVideoRecognitionLibraryApi.LibraryType,
): VxeTableGridOptions<AiVideoRecognitionLibraryApi.Entry>['columns'] {
  let externalTitle = '姿态编码';
  let nameTitle = '场景姿态';
  if (type === 'FACE') {
    externalTitle = '工号/人员编号';
    nameTitle = '人员姓名';
  } else if (type === 'PLATE') {
    externalTitle = '车牌号码';
    nameTitle = '车辆名称';
  }
  return [
    { field: 'media', slots: { default: 'media' }, title: '参考图', width: 86 },
    {
      field: 'name',
      minWidth: 150,
      title: nameTitle,
    },
    { field: 'externalCode', minWidth: 150, title: externalTitle },
    {
      field: 'attributes',
      minWidth: 220,
      slots: { default: 'attributes' },
      title: '业务属性',
    },
    {
      field: 'featureStatus',
      slots: { default: 'featureStatus' },
      title: '特征状态',
      width: 110,
    },
    { field: 'status', slots: { default: 'status' }, title: '状态', width: 90 },
    {
      field: 'actions',
      fixed: 'right',
      slots: { default: 'actions' },
      title: '操作',
      width: 150,
    },
  ];
}
