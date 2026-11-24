<script setup>
/**
 * This month's money on Home, for everyone (not only founders): what came in,
 * what went out, a quick way to jot down a new expense, and the latest few.
 * The same entries the Telegram bot writes; everything is in sums.
 */
import { computed, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'

import Icon from '@/components/ui/Icon.vue'
import { addCashFlow, listCashFlow } from '@/api/cashflow'
import { useAsyncData } from '@/composables/useAsyncData'
import { compactNumber, money, monthLabel } from '@/utils/format'

const CURRENCY = 'UZS'
const { locale } = useI18n()

const today = new Date()
const period = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`
const { data, reload } = useAsyncData(() => listCashFlow({ period }))
const totals = computed(() => data.value?.totals || { revenue: 0, spending: 0, net: 0 })
const recent = computed(() => (data.value?.entries || []).slice(0, 3))
const month = computed(() => monthLabel(period, locale.value))

const form = reactive({ entry_type: 'spending', category: '', amount: '' })
const saving = ref(false)
const saved = ref(false)
const error = ref(false)
let savedTimer = null

async function add() {
  const amount = String(form.amount).replace(/[\s ]/g, '').replace(',', '.')
  if (!amount || Number(amount) <= 0 || saving.value) return
  saving.value = true
  error.value = false
  try {
    await addCashFlow({ entry_type: form.entry_type, category: form.category.trim() || 'General', amount })
    form.amount = ''
    form.category = ''
    saved.value = true
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => (saved.value = false), 2000)
    await reload()
  } catch {
    error.value = true
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="card @container mb-5 p-4 sm:p-5">
    <div class="mb-4 flex items-center gap-3">
      <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300">
        <Icon name="wallet" class="h-5 w-5" />
      </span>
      <div class="min-w-0 flex-1">
        <h2 class="truncate text-lg font-bold leading-tight text-ink">{{ $t('cashWidget.title') }}</h2>
        <p class="truncate text-xs text-ink-muted">{{ month }} · {{ $t('cashWidget.inSums') }}</p>
      </div>
      <RouterLink
        :to="{ name: 'cashFlow' }"
        class="flex min-h-10 min-w-10 shrink-0 items-center justify-center gap-1 rounded-full px-2.5 text-sm font-semibold text-brand-700 hover:bg-brand-50 @md:px-3 dark:text-brand-300 dark:hover:bg-brand-500/10"
        :aria-label="$t('cashWidget.all')"
        :title="$t('cashWidget.all')"
      >
        <span class="hidden @md:inline">{{ $t('cashWidget.all') }}</span> <Icon name="arrowRight" class="h-4 w-4" />
      </RouterLink>
    </div>

    <dl class="grid grid-cols-3 gap-2 @sm:gap-3">
      <div class="min-w-0 rounded-2xl bg-mint/60 p-3 dark:bg-mint">
        <dt class="truncate text-xs font-medium text-ink-muted">{{ $t('dashboard.revenue') }}</dt>
        <dd :title="money(totals.revenue, CURRENCY)" class="mt-1 truncate text-base font-bold tabular-nums text-mint-ink @sm:text-lg">{{ compactNumber(totals.revenue) }}</dd>
      </div>
      <div class="min-w-0 rounded-2xl bg-red-50 p-3 dark:bg-red-500/10">
        <dt class="truncate text-xs font-medium text-ink-muted">{{ $t('dashboard.spending') }}</dt>
        <dd :title="money(totals.spending, CURRENCY)" class="mt-1 truncate text-base font-bold tabular-nums text-red-700 @sm:text-lg dark:text-red-300">{{ compactNumber(totals.spending) }}</dd>
      </div>
      <div class="min-w-0 rounded-2xl bg-brand-50 p-3 dark:bg-brand-500/10">
        <dt class="truncate text-xs font-medium text-ink-muted">{{ $t('dashboard.net') }}</dt>
        <dd :title="money(totals.net, CURRENCY)" class="mt-1 truncate text-base font-bold tabular-nums text-brand-700 @sm:text-lg dark:text-brand-300">{{ compactNumber(totals.net) }}</dd>
      </div>
    </dl>

    <!-- Jot down an expense (or income) without leaving Home. -->
    <form class="mt-4 flex flex-wrap gap-2" @submit.prevent="add">
      <div class="flex w-full rounded-xl bg-surface-2 p-1 @md:w-auto" role="radiogroup" :aria-label="$t('cashWidget.kind')">
        <button
          v-for="kind in ['spending', 'revenue']"
          :key="kind"
          type="button"
          role="radio"
          :aria-checked="form.entry_type === kind"
          class="min-h-10 flex-1 rounded-lg px-3 text-sm font-semibold transition @md:flex-none"
          :class="form.entry_type === kind
            ? (kind === 'spending' ? 'bg-white text-red-700 shadow-sm dark:bg-surface dark:text-red-300' : 'bg-white text-mint-ink shadow-sm dark:bg-surface')
            : 'text-ink-muted'"
          @click="form.entry_type = kind"
        >
          {{ $t(`cashWidget.${kind}`) }}
        </button>
      </div>
      <input
        v-model="form.amount"
        inputmode="decimal"
        autocomplete="off"
        :placeholder="$t('cashWidget.amount')"
        :aria-label="$t('cashWidget.amount')"
        class="zx-input h-11 min-w-0 flex-1 basis-32 tabular-nums"
      />
      <input
        v-model="form.category"
        maxlength="80"
        :placeholder="$t('cashWidget.category')"
        :aria-label="$t('cashWidget.category')"
        class="zx-input h-11 min-w-0 flex-1 basis-32"
      />
      <button
        type="submit"
        :disabled="saving || !form.amount"
        class="flex h-11 w-full items-center justify-center gap-1.5 rounded-xl bg-brand-600 px-4 text-sm font-bold text-white transition hover:bg-brand-700 disabled:opacity-50 @md:w-auto"
      >
        <Icon :name="saved ? 'check' : 'plus'" class="h-4 w-4" /> {{ saved ? $t('cashWidget.saved') : $t('common.add') }}
      </button>
    </form>
    <p v-if="error" role="alert" class="mt-2 text-sm text-red-600 dark:text-red-400">{{ $t('errors.generic') }}</p>

    <ul v-if="recent.length" class="mt-4 divide-y divide-hairline">
      <li v-for="e in recent" :key="e.id" class="flex items-center gap-3 py-2.5">
        <span
          class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
          :class="e.entry_type === 'revenue' ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15' : 'bg-red-50 text-red-600 dark:bg-red-500/15'"
        >
          <Icon :name="e.entry_type === 'revenue' ? 'trending' : 'wallet'" class="h-4 w-4" />
        </span>
        <span class="min-w-0 flex-1 truncate text-sm font-medium text-ink">{{ e.category }}</span>
        <span class="shrink-0 text-sm font-bold tabular-nums" :class="e.entry_type === 'revenue' ? 'text-mint-ink' : 'text-red-700 dark:text-red-300'">
          {{ e.entry_type === 'revenue' ? '+' : '−' }}{{ money(e.amount, CURRENCY) }}
        </span>
      </li>
    </ul>
    <p v-else-if="data" class="mt-4 text-sm text-ink-muted">{{ $t('cashWidget.empty') }}</p>

    <p class="mt-3 flex items-start gap-2 text-xs text-ink-muted">
      <Icon name="send" class="mt-0.5 h-3.5 w-3.5 shrink-0" /> {{ $t('cashWidget.bot') }}
    </p>
  </section>
</template>
