import type { VbenFormSchema } from '#/adapter/form';
import type { EvaluationCreate } from '#/api/ai-video/task/evaluation';

import { z } from '#/adapter/form';

export const metricFields = [
  ['eventPrecision', '事件准确率', 'minEventPrecision', '最低准确率', 0.9, 1],
  ['eventRecall', '事件召回率', 'minEventRecall', '最低召回率', 0.9, 1],
  [
    'falsePositivesPerStreamHour',
    '每路每小时误报',
    'maxFalsePositivesPerStreamHour',
    '最大误报',
    1,
  ],
  ['missedEvents', '漏报事件数', 'maxMissedEvents', '最大漏报', 0],
  [
    'endToEndP95Ms',
    '端到端 P95（ms）',
    'maxEndToEndP95Ms',
    '最大 P95（ms）',
    1500,
  ],
  ['averageFps', '平均分析 FPS', 'minAverageFps', '最低 FPS', 1],
] as const;

export const failedCheckLabels: Record<string, string> = Object.fromEntries([
  ...metricFields.map(([key, label]) => [key, label]),
  ['cooldownDedup', '冷却与去重'],
]);

function numberField(
  fieldName: string,
  label: string,
  maximum = 1_000_000_000,
  positive = false,
): VbenFormSchema {
  let rules = z
    .number({ required_error: '请填写实测值' })
    .finite()
    .min(positive ? 0.000001 : 0)
    .max(maximum);
  if (fieldName === 'missedEvents' || fieldName === 'maxMissedEvents')
    rules = rules.int();
  return {
    component: 'InputNumber',
    defaultValue: undefined,
    fieldName,
    label,
    rules,
    componentProps: {
      min: 0,
      max: maximum,
      class: 'w-full',
      precision:
        fieldName.includes('missed') || fieldName.includes('Missed') ? 0 : 6,
    },
  };
}

export function evaluationSchema(): VbenFormSchema[] {
  return [
    {
      component: 'Select',
      fieldName: 'taskId',
      defaultValue: undefined,
      label: '测试任务',
      rules: z.number().positive(),
      componentProps: {
        showSearch: true,
        filterOption: false,
        placeholder: '输入名称搜索任务（每次显示 20 条）',
      },
    },
    {
      component: 'DatePicker',
      fieldName: 'measuredAtMillis',
      label: '测试时间',
      rules: 'required',
      componentProps: { showTime: true, valueFormat: 'x', class: 'w-full' },
      defaultValue: String(Date.now()),
    },
    {
      component: 'Input',
      fieldName: 'datasetVersion',
      label: '测试集版本',
      rules: z.string().trim().min(1).max(100),
    },
    {
      component: 'Input',
      fieldName: 'datasetSha256',
      label: '测试集 SHA256',
      rules: z.string().regex(/^[a-f\d]{64}$/i, '请输入 64 位 SHA256'),
    },
    {
      component: 'Input',
      fieldName: 'evidenceRef',
      label: '证据引用',
      rules: z
        .string()
        .regex(
          /^[a-z\d][a-z\d._:/-]{0,511}$/i,
          '填写报告编号或对象键，不含签名参数',
        ),
      componentProps: { placeholder: 'reports/dataset-v1/run-001.json' },
    },
    {
      component: 'Textarea',
      fieldName: 'environmentDescription',
      label: '实测环境',
      rules: z.string().trim().min(1).max(1000),
      componentProps: {
        placeholder: '记录硬件、Runtime 版本、视频时长、光照及并发条件',
        rows: 2,
      },
    },
    ...metricFields.flatMap(
      ([key, label, threshold, thresholdLabel, defaultValue, maximum]) => [
        numberField(key, label, maximum),
        {
          ...numberField(
            threshold,
            thresholdLabel,
            maximum,
            threshold === 'minAverageFps' || threshold === 'maxEndToEndP95Ms',
          ),
          defaultValue,
        },
      ],
    ),
    numberField('cpuPeakPercent', 'CPU 峰值（%）', 100),
    numberField('memoryPeakMiB', '内存峰值（MiB）'),
    numberField('acceleratorMemoryPeakMiB', '加速器显存峰值（MiB）'),
    {
      component: 'Switch',
      fieldName: 'cooldownDedupPass',
      label: '冷却与去重通过',
      defaultValue: false,
    },
    {
      component: 'Textarea',
      fieldName: 'note',
      label: '备注',
      rules: z.string().max(2000).optional(),
      componentProps: { rows: 2 },
    },
  ];
}

export function evaluationPayload(
  values: Record<string, unknown>,
  configVersion: number,
  requestId: string,
  gatewayRevision = 0,
): EvaluationCreate {
  return {
    requestId,
    taskId: Number(values.taskId),
    expectedConfigVersion: configVersion,
    expectedGatewayRevision: gatewayRevision,
    measuredAtMillis: Number(values.measuredAtMillis),
    datasetVersion: String(values.datasetVersion).trim(),
    datasetSha256: String(values.datasetSha256).toLowerCase(),
    evidenceRef: String(values.evidenceRef).trim(),
    environmentDescription: String(values.environmentDescription).trim(),
    metrics: Object.fromEntries(
      metricFields.map(([key]) => [key, Number(values[key])]),
    ) as unknown as EvaluationCreate['metrics'],
    thresholds: Object.fromEntries(
      metricFields.map(([, , key]) => [key, Number(values[key])]),
    ) as unknown as EvaluationCreate['thresholds'],
    resourceUsage: {
      cpuPeakPercent: Number(values.cpuPeakPercent),
      memoryPeakMiB: Number(values.memoryPeakMiB),
      acceleratorMemoryPeakMiB: Number(values.acceleratorMemoryPeakMiB),
    },
    cooldownDedupPass: values.cooldownDedupPass === true,
    note: String(values.note ?? '').trim(),
  };
}
