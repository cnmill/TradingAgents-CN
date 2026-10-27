<template>
  <div class="stock-data-page">
    <div class="page-heading">
      <div>
        <h1>股票数据</h1>
        <p>输入 A 股代码，查看行情、基本面和历史 K 线。</p>
      </div>
      <div class="heading-actions">
        <el-button @click="router.push('/stock-data/list')">查看股票列表</el-button>
        <el-button :disabled="!symbol || loading" @click="loadStock">刷新数据</el-button>
      </div>
    </div>

    <el-card class="search-card" shadow="never">
      <div class="search-row">
        <el-input
          v-model="inputCode"
          clearable
          maxlength="6"
          placeholder="请输入 6 位股票代码，例如 000001"
          @keyup.enter="search"
        />
        <el-button type="primary" :loading="loading" @click="search">查询</el-button>
      </div>
      <div v-if="inputError" class="input-error">{{ inputError }}</div>
    </el-card>

    <template v-if="symbol">
      <el-alert v-if="dataError" class="notice" type="warning" :title="dataError" show-icon :closable="false" />
      <el-card class="quote-card" shadow="never" v-loading="loading">
        <template #header>
          <div class="section-header">
            <strong>{{ quote?.name || fundamentals?.name || symbol }}</strong>
            <span>{{ symbol }}<template v-if="quote?.trade_date"> · 交易日 {{ quote.trade_date }}</template></span>
          </div>
        </template>
        <div v-if="quote" class="quote-grid">
          <div><span>最新价</span><strong>{{ formatNumber(quote.price) }}</strong></div>
          <div><span>涨跌幅</span><strong :class="changeClass">{{ formatPercent(quote.change_percent) }}</strong></div>
          <div><span>昨收</span><strong>{{ formatNumber(quote.prev_close) }}</strong></div>
          <div><span>成交额</span><strong>{{ formatAmount(quote.amount) }}</strong></div>
          <div><span>换手率</span><strong>{{ formatPercent(quote.turnover_rate) }}</strong></div>
          <div><span>更新时间</span><strong>{{ quote.updated_at || '—' }}</strong></div>
        </div>
        <el-empty v-else-if="!loading" description="暂无行情数据" :image-size="72" />
      </el-card>

      <el-card class="section-card" shadow="never" v-loading="loading">
        <template #header><strong>基本面</strong></template>
        <el-descriptions v-if="fundamentals" :column="descriptionColumns" border>
          <el-descriptions-item label="名称">{{ fundamentals.name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="市场">{{ fundamentals.market || '—' }}</el-descriptions-item>
          <el-descriptions-item label="行业">{{ fundamentals.industry || '—' }}</el-descriptions-item>
          <el-descriptions-item label="总市值（亿元）">{{ formatNumber(fundamentals.total_mv) }}</el-descriptions-item>
          <el-descriptions-item label="市盈率">{{ formatNumber(fundamentals.pe_ttm ?? fundamentals.pe) }}</el-descriptions-item>
          <el-descriptions-item label="市净率">{{ formatNumber(fundamentals.pb_mrq ?? fundamentals.pb) }}</el-descriptions-item>
        </el-descriptions>
        <el-empty v-else-if="!loading" description="暂无基本面数据" :image-size="72" />
      </el-card>

      <div v-loading="klineLoading" class="chart-section">
        <KlineChart
          title="历史 K 线"
          :category="categories"
          :values="values"
          :volumes="volumes"
          :period="period"
          :period-options="periodOptions"
          :kline-source="kline?.source"
          :last-k-time="kline?.items.at(-1)?.time"
          :last-k-close="kline?.items.at(-1)?.close"
          @update-period="changePeriod"
        />
        <el-alert v-if="klineError" type="warning" :title="klineError" show-icon :closable="false" />
      </div>
      <div class="detail-link"><el-button link type="primary" @click="router.push(`/stocks/${symbol}`)">查看股票详情 →</el-button></div>
    </template>
    <el-empty v-else description="输入股票代码开始查看数据" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useWindowSize } from '@vueuse/core'
import { stocksApi } from '@/api/stocks'
import type { FundamentalsResponse, KlineResponse, QuoteResponse } from '@/api/stocks'
import KlineChart from './components/KlineChart.vue'

const route = useRoute()
const router = useRouter()
const { width } = useWindowSize()
const descriptionColumns = computed(() => width.value < 700 ? 1 : 3)
const inputCode = ref('')
const inputError = ref('')
const symbol = ref('')
const loading = ref(false)
const klineLoading = ref(false)
const dataError = ref('')
const klineError = ref('')
const quote = ref<QuoteResponse | null>(null)
const fundamentals = ref<FundamentalsResponse | null>(null)
const kline = ref<KlineResponse | null>(null)
const periodOptions = ['日线', '周线', '月线']
const period = ref('日线')
let requestId = 0
let klineRequestId = 0

const changeClass = computed(() => {
  const value = quote.value?.change_percent
  return value == null ? '' : value > 0 ? 'up' : value < 0 ? 'down' : ''
})
const validBars = computed(() => kline.value?.items.filter(item =>
  [item.open, item.close, item.low, item.high].every(value => value != null && Number.isFinite(Number(value)))
) || [])
const categories = computed(() => validBars.value.map(item => item.time))
const values = computed(() => validBars.value.map(item => [item.open, item.close, item.low, item.high].map(Number)))
const volumes = computed(() => validBars.value.map(item => Number(item.volume) || 0))

function formatNumber(value: number | null | undefined) {
  return value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toFixed(2)
}
function formatPercent(value: number | null | undefined) {
  return value == null || !Number.isFinite(Number(value)) ? '—' : `${Number(value).toFixed(2)}%`
}
function formatAmount(value: number | null | undefined) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  const amount = Number(value)
  return Math.abs(amount) >= 1e8 ? `${(amount / 1e8).toFixed(2)} 亿` : Math.abs(amount) >= 1e4 ? `${(amount / 1e4).toFixed(2)} 万` : amount.toFixed(2)
}

function search() {
  const code = inputCode.value.trim()
  if (!/^\d{6}$/.test(code)) {
    inputError.value = '请输入 6 位数字股票代码'
    return
  }
  inputError.value = ''
  symbol.value = code
  router.replace({ path: '/stock-data', query: { code } })
  loadStock()
}

async function loadKline() {
  const id = ++klineRequestId
  klineLoading.value = true
  klineError.value = ''
  kline.value = null
  const selectedPeriod = ({ 日线: 'day', 周线: 'week', 月线: 'month' } as const)[period.value as '日线' | '周线' | '月线']
  try {
    const response = await stocksApi.getKline(symbol.value, selectedPeriod, 120)
    if (id !== klineRequestId) return
    if (!response.success) throw new Error(response.message || 'K 线数据获取失败')
    kline.value = response.data
  } catch {
    if (id === klineRequestId) klineError.value = 'K 线数据获取失败，请稍后重试。'
  } finally {
    if (id === klineRequestId) klineLoading.value = false
  }
}

async function loadStock() {
  if (!symbol.value) return
  const id = ++requestId
  loading.value = true
  dataError.value = ''
  quote.value = null
  fundamentals.value = null
  void loadKline()
  const [quoteResult, fundamentalsResult] = await Promise.allSettled([
    stocksApi.getQuote(symbol.value),
    stocksApi.getFundamentals(symbol.value)
  ])
  if (id !== requestId) return
  if (quoteResult.status === 'fulfilled' && quoteResult.value.success) quote.value = quoteResult.value.data
  if (fundamentalsResult.status === 'fulfilled' && fundamentalsResult.value.success) fundamentals.value = fundamentalsResult.value.data
  if (!quote.value || !fundamentals.value) dataError.value = '部分股票数据未获取到，请稍后刷新重试。'
  loading.value = false
}

function changePeriod(nextPeriod: string) {
  period.value = nextPeriod
  if (symbol.value) void loadKline()
}

onMounted(() => {
  const code = typeof route.query.code === 'string' ? route.query.code : ''
  if (/^\d{6}$/.test(code)) {
    inputCode.value = code
    symbol.value = code
    loadStock()
  }
})
</script>

<style scoped>
.stock-data-page { max-width: 1200px; margin: 0 auto; padding: 24px; }
.page-heading, .section-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.page-heading { margin-bottom: 20px; }
.heading-actions { display: flex; gap: 8px; }
h1 { margin: 0 0 6px; font-size: 26px; }
p { margin: 0; color: var(--el-text-color-secondary); }
.search-card, .quote-card, .section-card, .chart-section { margin-bottom: 20px; }
.search-row { display: flex; gap: 12px; max-width: 500px; }
.input-error { margin-top: 8px; color: var(--el-color-danger); font-size: 13px; }
.notice { margin-bottom: 16px; }
.section-header span, .quote-grid span { color: var(--el-text-color-secondary); }
.quote-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 22px; }
.quote-grid > div { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.quote-grid strong { font-size: 20px; overflow-wrap: anywhere; }
.quote-grid .up { color: #e34d59; }
.quote-grid .down { color: #16a66a; }
.detail-link { text-align: right; }
@media (max-width: 700px) {
  .stock-data-page { padding: 12px; }
  .page-heading { align-items: flex-start; }
  .quote-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
