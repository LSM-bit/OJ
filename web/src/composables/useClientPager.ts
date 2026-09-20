/**
 * useClientPager —— 客户端分页
 *
 * 适用场景：数据量可能持续增长、但接口未提供分页参数的列表 / 表格。
 * 统一在此处预留分页入口，避免后期数据变大时页面被一次性渲染拖垮。
 *
 * 用法：
 *   const { page, size, total, paged } = useClientPager(computed(() => list.value), 20)
 *   模板里 v-for="item in paged"，底部放 <div class="pager-row"><el-pagination ... /></div>
 *
 * ⚠️ 硬性顺序约束：传进来的 source 依赖的变量（ref / computed）必须在**调用本函数之前**
 *    就已声明。内部 watch(total) 建订阅时会立刻读取一次 source，若源声明在调用之后，
 *    会抛 "Cannot access 'xxx' before initialization"（TDZ），setup 直接失败、整页空白。
 */
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'

export function useClientPager<T>(source: ComputedRef<T[]> | Ref<T[]>, pageSize = 10) {
  const page = ref(1)
  const size = ref(pageSize)
  const total = computed(() => source.value.length)
  const paged = computed(() => {
    const start = (page.value - 1) * size.value
    return source.value.slice(start, start + size.value)
  })
  // 数据增减导致当前页越界时回到第一页
  watch(total, () => {
    if ((page.value - 1) * size.value >= total.value) page.value = 1
  })
  return { page, size, total, paged }
}
