import { defineComponent, h } from 'vue';

/**
 * Compatibility-only replacement for the unmaintained WangEditor 4 adapter.
 * LInsight registers TinyMCE for real rich-text fields; this fallback deliberately
 * exposes only a plain textarea so unsafe HTML insertion cannot be reintroduced by
 * an indirect form-designer import.
 */
export default defineComponent({
  name: 'FcEditorSafeFallback',
  inheritAttrs: false,
  props: {
    disabled: Boolean,
    modelValue: {
      type: String,
      default: '',
    },
  },
  emits: ['update:modelValue'],
  setup(props, { attrs, emit }) {
    return () =>
      h('textarea', {
        ...attrs,
        disabled: props.disabled,
        value: props.modelValue,
        onInput: (event) => emit('update:modelValue', event.target.value),
      });
  },
});
