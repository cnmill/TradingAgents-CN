<template>
  <div class="stock-list-page">
    <div class="page-heading">
      <div>
        <h1>股票数据列表</h1>
        <p>浏览已入库的 A 股基础信息，点击股票查看行情和 K 线。</p>
      </div>
      <div class="actions">
        <el-button @click="router.push('/stock-data')">按代码查询</el-button>
        <el-button :loading="loading" @click="loadList">刷新</el-button>
      </div>
    </div>

    <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" class="notice" />
    <el-card shadow="never">
      <el-table :data="items" v-loading="loading" stripe row-key="symbol" style="width: 100%" empty-text="暂无股票数据">
        <el-table-column label="代码" prop="symbol" width="110" fixed />
        <el-table-column label="名称" prop="name" min-width="130" show-overflow-tooltip />
        <el-table-column label="市场" prop="market" min-width="110" show-overflow-tooltip>
          <template #default="{ row }">{{ row.market || '—' }}</template>
        </el-table-column>
        <el-table-column label="行业" prop="industry" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">{{ row.industry || '—' }}</template>
        </el-table-column>
        <el-table-column label="地区" prop="area" min-width="100" show-overflow-tooltip>
          <template #default="{ row }">{{ row.area || '—' }}</template>
        </el-table-column>
        <el-table-column label="总市值（亿元）" min-width="125" align="right">
          <template #default="{ row }">{{ formatNumber(row.total_mv) }}</template>
        </el-table-column>
        <el-table-column label="市盈率" min-width="100" align="right">
          <template #default="{ row }">{{ formatNumber(row.pe_ttm ?? row.pe) }}</template>
        </el-table-column>
        <el-table-column label="上市日期" min-width="120">
          <template #default="{ row }">{{ row.list_date || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="105" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openStock(row.symbol)">查看数据</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <span>第 {{ page }} 页 · 每页 {{ pageSize }} 条</span>
        <div class="actions">
          <el-button :disabled="loading || page === 1" @click="changePage(page - 1)">上一页</el-button>
          <el-button :disabled="loading || items.length < pageSize" @click="changePage(page + 1)">下一页</el-button>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { stocksApi } from '@/api/stocks'
import type { StockListItem } from '@/api/stocks'

const router = useRouter()
const items = ref<StockListItem[]>([])
const loading = ref(false)
const error = ref('')
const page = ref(1)
const pageSize = 20
let requestId = 0

function formatNumber(value?: number | null) {
  return value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toFixed(2)
}

async function loadList() {
  const id = ++requestId
  loading.value = true
  error.value = ''
  try {
    const response = await stocksApi.getList(page.value, pageSize)
    if (id !== requestId) return
    if (!response.success) throw new Error(response.message || '获取股票列表失败')
    items.value = response.data || []
  } catch {
    if (id === requestId) {
      items.value = []
      error.value = '股票列表加载失败，请稍后刷新重试。'
    }
  } finally {
    if (id === requestId) loading.value = false
  }
}

function changePage(nextPage: number) {
  page.value = nextPage
  void loadList()
}

function openStock(symbol: string) {
  router.push({ path: '/stock-data', query: { code: symbol } })
}

onMounted(loadList)
</script>

<style scoped>
.stock-list-page { max-width: 1400px; margin: 0 auto; padding: 24px; }
.page-heading, .pagination, .actions { display: flex; align-items: center; gap: 10px; }
.page-heading, .pagination { justify-content: space-between; }
.page-heading { margin-bottom: 20px; }
h1 { margin: 0 0 6px; font-size: 26px; }
p, .pagination span { margin: 0; color: var(--el-text-color-secondary); }
.notice { margin-bottom: 16px; }
.pagination { margin-top: 16px; }
@media (max-width: 700px) {
  .stock-list-page { padding: 12px; }
  .page-heading { align-items: flex-start; flex-direction: column; }
}
</style>
