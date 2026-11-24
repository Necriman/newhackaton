<script setup>
import { computed, reactive, ref } from 'vue'

import Icon from '@/components/ui/Icon.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { useCashFlow } from '@/composables/useStartup'
import { addCashFlow, deleteCashFlow } from '@/api/cashflow'
import { compactNumber, money } from '@/utils/format'

const { data, reload } = useCashFlow()
const entries = computed(() => data.value?.entries || [])
const totals = computed(() => data.value?.totals || { revenue: '0', spending: '0', net: '0' })
// The cash flow is kept in sums, the same as the Telegram bot writes it.
const currency = 'UZS'

const form = reactive({ entry_type: 'revenue', category: '', amount: '' })
const saving = ref(false)

async function add() {
  if (!form.amount) return
  saving.value = true
  try {
    await addCashFlow({
      entry_type: form.entry_type,
      category: form.category || 'General',
      amount: form.amount,
    })
    form.category = ''
    form.amount = ''
    await reload()
  } finally {
    saving.value = false
  }
}

async function remove(id) {
  await deleteCashFlow(id)
  await reload()
}
</script>

<template>
  <div>
    <h1 class="text-2xl font-extrabold tracking-tight text-slate-900 dark:text-white">
      {{ $t('dashboard.cashFlowTitle') }}
    </h1>
    <p class="mb-6 mt-1 text-sm text-slate-500">{{ $t('cashWidget.allInSums') }}</p>

    <!-- Totals -->
    <div class="mb-6 grid grid-cols-3 gap-2 sm:gap-4">
      <div class="card min-w-0 p-3 sm:p-5">
        <p class="truncate text-xs font-medium text-green-600">{{ $t('dashboard.revenue') }}</p>
        <p class="mt-1 truncate text-base font-extrabold tabular-nums sm:text-2xl text-green-700 dark:text-green-400"><span class="sm:hidden" :title="money(totals.revenue, currency)">{{ compactNumber(totals.revenue) }}</span><span class="hidden sm:inline">{{ money(totals.revenue, currency) }}</span></p>
      </div>
      <div class="card min-w-0 p-3 sm:p-5">
        <p class="truncate text-xs font-medium text-red-600">{{ $t('dashboard.spending') }}</p>
        <p class="mt-1 truncate text-base font-extrabold tabular-nums sm:text-2xl text-red-700 dark:text-red-400"><span class="sm:hidden" :title="money(totals.spending, currency)">{{ compactNumber(totals.spending) }}</span><span class="hidden sm:inline">{{ money(totals.spending, currency) }}</span></p>
      </div>
      <div class="card min-w-0 p-3 sm:p-5">
        <p class="truncate text-xs font-medium text-brand-600">{{ $t('dashboard.net') }}</p>
        <p class="mt-1 truncate text-base font-extrabold tabular-nums sm:text-2xl text-brand-700 dark:text-brand-400"><span class="sm:hidden" :title="money(totals.net, currency)">{{ compactNumber(totals.net) }}</span><span class="hidden sm:inline">{{ money(totals.net, currency) }}</span></p>
      </div>
    </div>

    <!-- Add form -->
    <form class="card mb-6 flex flex-wrap items-end gap-3 p-5" @submit.prevent="add">
      <select
        v-model="form.entry_type"
        class="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-hairline dark:bg-surface-2"
      >
        <option value="revenue">{{ $t('dashboard.revenue') }}</option>
        <option value="spending">{{ $t('dashboard.spending') }}</option>
      </select>
      <input
        v-model="form.category"
        :placeholder="$t('misc.category')"
        class="min-w-0 flex-1 basis-40 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-hairline dark:bg-surface-2"
      />
      <input
        v-model="form.amount"
        type="number"
        step="0.01"
        min="0"
        :placeholder="$t('misc.amount')"
        class="w-full min-w-0 flex-1 rounded-lg border sm:w-32 sm:flex-none border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-hairline dark:bg-surface-2"
      />
      <button
        type="submit"
        :disabled="saving"
        class="pill bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50"
      >
        <Icon name="plus" class="h-4 w-4" /> {{ $t('common.add') }}
      </button>
    </form>

    <!-- Entries -->
    <div class="card divide-y divide-slate-100 dark:divide-hairline">
      <EmptyState v-if="!entries.length" icon="wallet" :message="$t('common.nothingYet')" />
      <div v-for="e in entries" :key="e.id" class="flex items-center gap-3 p-3 sm:gap-4 sm:p-4">
        <span
          class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl"
          :class="e.entry_type === 'revenue' ? 'bg-green-50 text-green-600 dark:bg-green-500/15' : 'bg-red-50 text-red-600 dark:bg-red-500/15'"
        >
          <Icon :name="e.entry_type === 'revenue' ? 'trending' : 'wallet'" class="h-4 w-4" />
        </span>
        <div class="min-w-0 flex-1">
          <p class="truncate font-medium text-slate-800 dark:text-ink">{{ e.category }}</p>
          <p class="text-xs text-slate-400">{{ e.occurred_on }}</p>
        </div>
        <span
          class="shrink-0 text-sm font-bold tabular-nums sm:text-base"
          :class="e.entry_type === 'revenue' ? 'text-green-600' : 'text-red-600'"
        >
          {{ e.entry_type === 'revenue' ? '+' : '−' }}{{ money(e.amount, currency) }}
        </span>
        <button type="button" class="-m-2 shrink-0 p-2 text-slate-300 hover:text-red-500" :aria-label="$t('common.delete')" @click="remove(e.id)">
          <Icon name="x" class="h-4 w-4" />
        </button>
      </div>
    </div>
  </div>
</template>
