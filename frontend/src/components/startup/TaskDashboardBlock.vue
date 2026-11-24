<script setup>
/**
 * The founder's task board. A task goes to one employee with details, a
 * priority and dates; the employee gets it by e-mail with a page of its own to
 * answer from (accepted, in progress, done, a note — startup/assign.py). The
 * board shows where each task stands, whether the letter went out, and what the
 * employee wrote back.
 */
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import Icon from '@/components/ui/Icon.vue'
import Avatar from '@/components/ui/Avatar.vue'
import CheckBox from '@/components/ui/CheckBox.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import BlockCard from './BlockCard.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { dateTime } from '@/utils/format'
import {
  createAssignment,
  deleteAssignment,
  listAssignments,
  listEmployees,
  notifyAssignment,
  updateAssignment,
} from '@/api/startup'

const { t, locale } = useI18n()
const props = defineProps({ rosterVersion: Number })

const { data: assignData, reload } = useAsyncData(listAssignments)
const { data: empData, reload: reloadEmployees } = useAsyncData(listEmployees)
watch(() => props.rosterVersion, () => Promise.all([reloadEmployees(), reload()]).catch(fail))
const assignments = computed(() => assignData.value?.assignments || [])
const employees = computed(() => empData.value?.employees || [])

const PRIORITIES = ['low', 'normal', 'high']
const blank = () => ({ employee: '', title: '', description: '', priority: 'normal', start_date: '', end_date: '', notify: true })
const form = reactive(blank())
const adding = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref(null) // { tone: 'ok' | 'warn', text }
const filter = ref('active')
const expanded = ref(null)
const confirming = ref(null)

const chosen = computed(() => employees.value.find((e) => e.id === form.employee) || null)
const canMail = computed(() => !!chosen.value?.email && !chosen.value?.email_opt_out)

const today = new Date().toISOString().slice(0, 10)
const isOverdue = (a) => !a.done && !!a.end_date && a.end_date < today
const counts = computed(() => ({
  active: assignments.value.filter((a) => !a.done).length,
  done: assignments.value.filter((a) => a.done).length,
  all: assignments.value.length,
}))
const shown = computed(() => {
  const list = assignments.value.filter((a) => (filter.value === 'all' ? true : filter.value === 'done' ? a.done : !a.done))
  // Overdue and urgent first among the open ones; the server keeps the rest in date order.
  const weight = (a) => (a.done ? 2 : isOverdue(a) ? 0 : a.priority === 'high' ? 0.5 : 1)
  return [...list].sort((x, y) => weight(x) - weight(y))
})

function fail(e) {
  error.value = e?.response?.data?.detail || e?.message || t('misc.saveFailed')
}

function letterNotice(letter, email) {
  if (letter?.sent) return { tone: 'ok', text: t('assignTask.sentTo', { email: letter.to || email }) }
  if (letter?.reason === 'failed') return { tone: 'warn', text: t('assignTask.letterFailed') }
  if (letter?.reason === 'rate_limited') return { tone: 'warn', text: t('assignTask.rateLimited') }
  return { tone: 'ok', text: t('assignTask.savedNoLetter') }
}

function openForm() {
  adding.value = !adding.value
  error.value = ''
  if (adding.value && !form.employee && employees.value.length === 1) form.employee = employees.value[0].id
}

async function save() {
  if (!form.employee || !form.title.trim() || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const res = await createAssignment({
      employee: form.employee,
      title: form.title,
      description: form.description,
      priority: form.priority,
      start_date: form.start_date || null,
      end_date: form.end_date || null,
      notify: form.notify && canMail.value,
    })
    notice.value = letterNotice(res.letter, chosen.value?.email)
    Object.assign(form, blank())
    adding.value = false
    filter.value = 'active'
    await reload()
  } catch (e) {
    fail(e)
  } finally {
    busy.value = false
  }
}

async function toggle(a) {
  try {
    await updateAssignment(a.id, { status: a.done ? 'in_progress' : 'done' })
    await reload()
  } catch (e) {
    fail(e)
  }
}

async function resend(a) {
  error.value = ''
  try {
    const res = await notifyAssignment(a.id)
    notice.value = { tone: 'ok', text: t('assignTask.resent', { email: res.letter.to }) }
    await reload()
  } catch (e) {
    const letter = e?.response?.data?.letter
    if (letter) notice.value = letterNotice(letter)
    else fail(e)
  }
}

async function remove(a) {
  if (confirming.value !== a.id) {
    confirming.value = a.id
    return
  }
  try {
    await deleteAssignment(a.id)
    confirming.value = null
    expanded.value = null
    await reload()
  } catch (e) {
    fail(e)
  }
}

function fmtDate(iso) {
  if (!iso) return ''
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}

const STATUS_STYLE = {
  new: 'bg-slate-100 text-slate-600 dark:bg-surface-2 dark:text-slate-300',
  accepted: 'bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300',
  in_progress: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',
  done: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
}
</script>

<template>
  <BlockCard
    icon="taskList"
    iconColor="text-violet-600"
    iconBg="bg-violet-50 dark:bg-violet-500/15"
    :title="$t('startup.tasks.title')"
    :subtitle="$t('startup.tasks.subtitle')"
  >
    <template #action>
      <button
        type="button"
        :disabled="!employees.length"
        class="flex min-h-9 items-center gap-1 rounded-lg px-2.5 text-sm font-semibold text-brand-600 transition hover:bg-brand-50 disabled:opacity-40 dark:hover:bg-brand-500/10"
        :aria-expanded="adding"
        @click="openForm"
      >
        <Icon :name="adding ? 'x' : 'plus'" class="h-4 w-4" />
        {{ adding ? $t('common.cancel') : $t('assignTask.newTitle') }}
      </button>
    </template>

    <p v-if="!employees.length" class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-500 dark:bg-surface-2">
      {{ $t('startup.tasks.needEmployees') }}
    </p>

    <!-- What happened to the last action, the letter above all. -->
    <div
      v-if="notice"
      role="status"
      class="mb-3 flex items-start gap-2 rounded-xl px-3 py-2.5 text-sm"
      :class="notice.tone === 'ok' ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-500/10 dark:text-emerald-200' : 'bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:text-amber-200'"
    >
      <Icon :name="notice.tone === 'ok' ? 'mail' : 'alert'" class="mt-0.5 h-4 w-4 shrink-0" />
      <span class="min-w-0 flex-1 break-words">{{ notice.text }}</span>
      <button type="button" class="-m-1 shrink-0 rounded p-1 opacity-60 hover:opacity-100" :aria-label="$t('common.close')" @click="notice = null">
        <Icon name="x" class="h-3.5 w-3.5" />
      </button>
    </div>

    <!-- Hand a task out. -->
    <form v-if="adding && employees.length" class="mb-4 space-y-3 rounded-2xl border border-hairline bg-slate-50/70 p-3 sm:p-4 dark:bg-surface-2" @submit.prevent="save">
      <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400">
        {{ $t('assignTask.who') }}
        <select v-model="form.employee" required class="zx-input mt-1 w-full py-2 text-sm font-normal">
          <option value="" disabled>{{ $t('startup.tasks.selectEmployee') }}</option>
          <option v-for="e in employees" :key="e.id" :value="e.id">{{ e.full_name }}{{ e.position ? ` · ${e.position}` : '' }}</option>
        </select>
      </label>

      <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400">
        {{ $t('assignTask.what') }}
        <input v-model="form.title" required maxlength="200" :placeholder="$t('assignTask.whatPlaceholder')" class="zx-input mt-1 w-full py-2 text-sm font-normal" />
      </label>

      <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400">
        {{ $t('assignTask.details') }}
        <textarea v-model="form.description" rows="3" maxlength="4000" :placeholder="$t('assignTask.detailsPlaceholder')" class="zx-input mt-1 w-full resize-y py-2 text-sm font-normal" />
      </label>

      <div class="grid grid-cols-1 gap-3 sm:grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)] sm:items-end">
        <div>
          <p class="text-xs font-semibold text-slate-500 dark:text-slate-400">{{ $t('assignTask.priority') }}</p>
          <div class="mt-1 flex rounded-xl bg-white p-1 dark:bg-surface" role="radiogroup" :aria-label="$t('assignTask.priority')">
            <button
              v-for="p in PRIORITIES"
              :key="p"
              type="button"
              role="radio"
              :aria-checked="form.priority === p"
              class="min-h-9 flex-1 rounded-lg px-3 text-sm font-semibold transition sm:flex-none"
              :class="form.priority === p ? (p === 'high' ? 'bg-red-600 text-white' : 'bg-brand-600 text-white') : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'"
              @click="form.priority = p"
            >
              {{ $t(`assignTask.${p}`) }}
            </button>
          </div>
        </div>
        <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400">
          {{ $t('assignTask.start') }}
          <input v-model="form.start_date" type="date" class="zx-input mt-1 w-full py-2 text-sm font-normal" />
        </label>
        <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400">
          {{ $t('assignTask.deadline') }}
          <input v-model="form.end_date" type="date" :min="form.start_date || undefined" class="zx-input mt-1 w-full py-2 text-sm font-normal" />
        </label>
      </div>

      <!-- The letter: on by default when the employee has an address. -->
      <div v-if="chosen" class="rounded-xl bg-white px-3 py-2.5 text-sm dark:bg-surface">
        <label v-if="canMail" class="flex cursor-pointer items-start gap-2.5">
          <input v-model="form.notify" type="checkbox" class="mt-0.5 h-4 w-4 shrink-0 accent-brand-600" />
          <span class="min-w-0 break-words text-slate-700 dark:text-slate-200">{{ $t('assignTask.notify', { email: chosen.email }) }}</span>
        </label>
        <p v-else-if="chosen.email_opt_out" class="flex items-start gap-2 text-amber-700 dark:text-amber-300">
          <Icon name="mail" class="mt-0.5 h-4 w-4 shrink-0" />{{ $t('assignTask.optedOut', { name: chosen.full_name }) }}
        </p>
        <p v-else class="flex items-start gap-2 text-amber-700 dark:text-amber-300">
          <Icon name="mail" class="mt-0.5 h-4 w-4 shrink-0" />{{ $t('assignTask.noEmail', { name: chosen.full_name }) }}
        </p>
      </div>

      <p v-if="error" role="alert" class="text-sm text-red-600 dark:text-red-400">{{ error }}</p>
      <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button type="button" class="min-h-10 rounded-xl px-4 text-sm font-semibold text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-surface" @click="adding = false">{{ $t('common.cancel') }}</button>
        <button type="submit" :disabled="busy || !form.employee || !form.title.trim()" class="flex min-h-10 items-center justify-center gap-1.5 rounded-xl bg-brand-600 px-5 text-sm font-bold text-white hover:bg-brand-700 disabled:opacity-40">
          <Icon :name="form.notify && canMail ? 'send' : 'check'" class="h-4 w-4" /> {{ $t('assignTask.submit') }}
        </button>
      </div>
    </form>

    <template v-if="employees.length">
      <!-- Open / done / all. -->
      <div v-if="assignments.length" class="mb-3 flex gap-1 overflow-x-auto" role="tablist">
        <button
          v-for="f in ['active', 'done', 'all']"
          :key="f"
          type="button"
          role="tab"
          :aria-selected="filter === f"
          class="flex min-h-8 shrink-0 items-center gap-1.5 rounded-full px-3 text-xs font-semibold transition"
          :class="filter === f ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-surface-2 dark:text-slate-300'"
          @click="filter = f"
        >
          {{ $t(`assignTask.filter_${f}`) }}
          <span class="tabular-nums opacity-70">{{ counts[f] }}</span>
        </button>
      </div>

      <EmptyState v-if="!assignments.length" icon="taskList" :message="$t('startup.tasks.empty')" />
      <p v-else-if="!shown.length" class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-500 dark:bg-surface-2">{{ $t('assignTask.emptyFilter') }}</p>

      <ul v-else class="space-y-2">
        <li v-for="a in shown" :key="a.id" class="rounded-xl border border-hairline transition" :class="expanded === a.id ? 'bg-slate-50/70 dark:bg-surface-2' : ''">
          <div class="flex items-start gap-3 p-2.5">
            <CheckBox :model-value="a.done" shape="square" class="mt-0.5 shrink-0" :aria-label="a.done ? $t('assignTask.reopen') : $t('assignTask.markDone')" @update:model-value="toggle(a)" />
            <button type="button" class="min-w-0 flex-1 text-left" :aria-expanded="expanded === a.id" @click="expanded = expanded === a.id ? null : a.id">
              <p class="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span class="min-w-0 break-words text-sm font-semibold" :class="a.done ? 'text-slate-400 line-through' : 'text-slate-800 dark:text-ink'">{{ a.title }}</span>
                <span v-if="a.priority === 'high' && !a.done" class="rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-bold text-red-700 dark:bg-red-500/15 dark:text-red-300">{{ $t('assignTask.high') }}</span>
              </p>
              <p class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
                <span class="flex items-center gap-1.5">
                  <Avatar :name="a.employee_name" size="h-5 w-5 text-[9px]" />
                  <span class="font-medium text-slate-700 dark:text-slate-200">{{ a.employee_name }}</span>
                </span>
                <span class="rounded-full px-2 py-0.5 font-semibold" :class="STATUS_STYLE[a.status]">{{ $t(`assignTask.status_${a.status}`) }}</span>
                <span v-if="a.end_date" class="tabular-nums" :class="isOverdue(a) ? 'font-semibold text-red-600 dark:text-red-400' : ''">
                  {{ isOverdue(a) ? $t('assignTask.overdue') + ' · ' : '' }}{{ $t('assignTask.due', { date: fmtDate(a.end_date) }) }}
                </span>
                <span class="flex items-center gap-1" :title="a.notified_at ? $t('assignTask.mailed', { when: dateTime(a.notified_at, locale) }) : $t('assignTask.notMailed')">
                  <Icon name="mail" class="h-3.5 w-3.5" :class="a.notified_at ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-300 dark:text-slate-600'" />
                  <span class="sr-only">{{ a.notified_at ? $t('assignTask.mailed', { when: dateTime(a.notified_at, locale) }) : $t('assignTask.notMailed') }}</span>
                </span>
                <span v-if="a.note" class="flex items-center gap-1 text-brand-600 dark:text-brand-300"><Icon name="note" class="h-3.5 w-3.5" />{{ $t('assignTask.hasNote') }}</span>
              </p>
            </button>
            <Icon name="chevronRight" class="mt-1 h-4 w-4 shrink-0 text-slate-300 transition" :class="expanded === a.id ? 'rotate-90' : ''" />
          </div>

          <!-- Details, the employee's answer, the letter. -->
          <div v-if="expanded === a.id" class="space-y-3 border-t border-hairline px-3 py-3 text-sm">
            <p v-if="a.description" class="whitespace-pre-wrap break-words text-slate-700 dark:text-slate-200">{{ a.description }}</p>
            <p v-else class="text-slate-400">{{ $t('assignTask.noDetails') }}</p>
            <p v-if="a.start_date" class="text-xs text-slate-500">{{ $t('assignTask.start') }}: <span class="tabular-nums">{{ fmtDate(a.start_date) }}</span></p>
            <blockquote v-if="a.note" class="rounded-xl border-l-4 border-brand-500 bg-white px-3 py-2 dark:bg-surface">
              <p class="text-xs font-semibold text-brand-700 dark:text-brand-300">{{ $t('assignTask.note') }}</p>
              <p class="mt-0.5 whitespace-pre-wrap break-words text-slate-700 dark:text-slate-200">{{ a.note }}</p>
            </blockquote>
            <p class="text-xs text-slate-500">
              <template v-if="a.notified_at">{{ $t('assignTask.mailed', { when: dateTime(a.notified_at, locale) }) }} · {{ a.employee_email }}</template>
              <template v-else-if="a.letters_off">{{ $t('assignTask.optedOut', { name: a.employee_name }) }}</template>
              <template v-else-if="!a.employee_email">{{ $t('assignTask.noEmail', { name: a.employee_name }) }}</template>
              <template v-else>{{ $t('assignTask.notMailed') }}</template>
            </p>
            <div class="flex flex-wrap gap-2">
              <button type="button" class="flex min-h-9 items-center gap-1.5 rounded-lg border border-hairline px-3 text-xs font-semibold hover:bg-white dark:hover:bg-surface" @click="toggle(a)">
                <Icon :name="a.done ? 'refresh' : 'check'" class="h-3.5 w-3.5" />{{ a.done ? $t('assignTask.reopen') : $t('assignTask.markDone') }}
              </button>
              <button v-if="a.employee_email && !a.letters_off" type="button" class="flex min-h-9 items-center gap-1.5 rounded-lg border border-hairline px-3 text-xs font-semibold hover:bg-white dark:hover:bg-surface" @click="resend(a)">
                <Icon name="send" class="h-3.5 w-3.5" />{{ a.notified_at ? $t('assignTask.resend') : $t('assignTask.sendNow') }}
              </button>
              <button type="button" class="ml-auto flex min-h-9 items-center gap-1.5 rounded-lg px-3 text-xs font-semibold" :class="confirming === a.id ? 'bg-red-600 text-white' : 'text-slate-400 hover:text-red-600'" @click="remove(a)">
                <Icon name="trash" class="h-3.5 w-3.5" />{{ confirming === a.id ? $t('assignTask.confirmDelete') : $t('common.delete') }}
              </button>
            </div>
          </div>
        </li>
      </ul>
      <p v-if="error && !adding" role="alert" class="mt-2 text-sm text-red-600 dark:text-red-400">{{ error }}</p>
    </template>
  </BlockCard>
</template>
