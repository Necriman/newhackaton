<script setup>
/**
 * One task, as the employee sees it: opened from the letter the founder's
 * assignment sent (/task/<secret>), with no account. They read it, move it
 * along (accept → in progress → done), write a word back, or turn the letters
 * off. The secret in the address is the only key (startup/assign.py).
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'

import BrandMark from '@/components/ui/BrandMark.vue'
import Icon from '@/components/ui/Icon.vue'
import LanguageSwitcher from '@/components/ui/LanguageSwitcher.vue'
import BearSticker from '@/components/mascot/BearSticker.vue'
import { getTaskPage, updateTaskPage } from '@/api/startup'

const route = useRoute()
const { t } = useI18n()
const secret = String(route.params.secret || '')

const task = ref(null)
const state = ref('loading') // loading | ready | invalid | error
const busy = ref(false)
const flash = ref('')
const error = ref('')
const note = ref('')
const noteSent = ref(false)
let flashTimer = null

// A task page is private: keep it out of search engines even if a link leaks.
const robots = document.createElement('meta')
robots.name = 'robots'
robots.content = 'noindex, nofollow'
document.head.appendChild(robots)
onBeforeUnmount(() => {
  robots.remove()
  clearTimeout(flashTimer)
})

async function load() {
  state.value = 'loading'
  try {
    task.value = (await getTaskPage(secret)).task
    note.value = task.value.note || ''
    document.title = `${task.value.title} · Zinvest`
    state.value = 'ready'
  } catch (e) {
    state.value = e?.response?.status === 404 ? 'invalid' : 'error'
  }
}
onMounted(load)

async function send(payload, message) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    task.value = (await updateTaskPage(secret, payload)).task
    flash.value = message
    clearTimeout(flashTimer)
    flashTimer = setTimeout(() => (flash.value = ''), 3500)
    return true
  } catch (e) {
    error.value = e?.response?.data?.detail || t('errors.generic')
    return false
  } finally {
    busy.value = false
  }
}

const STEPS = ['new', 'accepted', 'in_progress', 'done']
const step = computed(() => STEPS.indexOf(task.value?.status))
const next = computed(() => ({
  new: { status: 'accepted', label: t('taskPage.accept'), icon: 'check' },
  accepted: { status: 'in_progress', label: t('taskPage.start'), icon: 'play' },
  in_progress: { status: 'done', label: t('taskPage.done'), icon: 'checkCircle' },
}[task.value?.status] || null))

function move(status) {
  send({ status }, t('taskPage.saved', { founder: task.value.founder_name }))
}
async function sendNote() {
  if (await send({ note: note.value }, t('taskPage.noteSent'))) noteSent.value = true
}
function lettersOff() {
  send({ letters_off: true }, t('taskPage.lettersOffDone'))
}

function fmtDate(iso) {
  if (!iso) return ''
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}
const overdue = computed(() => task.value?.end_date && task.value.status !== 'done' && task.value.end_date < new Date().toISOString().slice(0, 10))
</script>

<template>
  <div class="min-h-dvh bg-canvas px-4 py-6 sm:py-10">
    <div class="mx-auto w-full max-w-xl">
      <header class="mb-5 flex items-center justify-between gap-3">
        <RouterLink :to="{ name: 'landing' }" class="flex items-center gap-2" :aria-label="$t('taskPage.about')">
          <BrandMark class="h-8 w-8" />
          <span class="text-lg font-extrabold tracking-tight text-slate-900 dark:text-white">Zinvest</span>
        </RouterLink>
        <LanguageSwitcher />
      </header>

      <!-- Loading -->
      <div v-if="state === 'loading'" class="card flex justify-center p-10" role="status" :aria-label="$t('common.loading')">
        <BearSticker name="think" float class="h-28 w-28" />
      </div>

      <!-- A dead or mistyped link -->
      <div v-else-if="state === 'invalid' || state === 'error'" class="card p-6 text-center sm:p-8">
        <BearSticker name="confused" pop class="mx-auto h-32 w-32" />
        <h1 class="mt-2 text-xl font-extrabold text-slate-900 dark:text-white">{{ state === 'invalid' ? $t('taskPage.invalid') : $t('errors.generic') }}</h1>
        <p v-if="state === 'invalid'" class="mt-2 text-slate-600 dark:text-slate-300">{{ $t('taskPage.invalidHint') }}</p>
        <button v-else type="button" class="mt-5 min-h-11 rounded-xl bg-brand-600 px-5 font-semibold text-white" @click="load">{{ $t('business.retry') }}</button>
      </div>

      <!-- The task -->
      <article v-else class="card overflow-hidden">
        <div class="p-5 sm:p-7">
          <p class="text-xs font-bold uppercase tracking-wider text-brand-600 dark:text-brand-300">{{ $t('taskPage.eyebrow') }}</p>
          <h1 class="mt-1.5 break-words text-2xl font-extrabold leading-tight tracking-tight text-slate-900 sm:text-3xl dark:text-white">{{ task.title }}</h1>
          <p class="mt-2 text-sm text-slate-500 dark:text-slate-400">
            {{ $t('taskPage.from', { founder: task.founder_name, business: task.business_name }) }}
            <span class="mx-1 text-slate-300">·</span>{{ $t('taskPage.for', { name: task.employee_name }) }}
          </p>

          <div class="mt-4 flex flex-wrap gap-2 text-sm">
            <span v-if="task.priority === 'high'" class="rounded-full bg-red-50 px-3 py-1 font-bold text-red-700 dark:bg-red-500/15 dark:text-red-300">{{ $t('assignTask.high') }}</span>
            <span v-else class="rounded-full bg-slate-100 px-3 py-1 font-semibold text-slate-600 dark:bg-surface-2 dark:text-slate-300">{{ $t('assignTask.priority') }}: {{ $t(`assignTask.${task.priority}`) }}</span>
            <span v-if="task.start_date" class="rounded-full bg-slate-100 px-3 py-1 tabular-nums text-slate-600 dark:bg-surface-2 dark:text-slate-300">{{ $t('assignTask.start') }}: {{ fmtDate(task.start_date) }}</span>
            <span v-if="task.end_date" class="rounded-full px-3 py-1 font-semibold tabular-nums" :class="overdue ? 'bg-red-50 text-red-700 dark:bg-red-500/15 dark:text-red-300' : 'bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-300'">
              {{ overdue ? $t('assignTask.overdue') + ' · ' : '' }}{{ $t('assignTask.deadline') }}: {{ fmtDate(task.end_date) }}
            </span>
          </div>

          <p v-if="task.description" class="mt-5 whitespace-pre-wrap break-words rounded-2xl bg-slate-50 p-4 leading-relaxed text-slate-700 dark:bg-surface-2 dark:text-slate-200">{{ task.description }}</p>
        </div>

        <!-- Where it stands, and the next step -->
        <section class="border-t border-hairline bg-slate-50/60 p-5 sm:p-7 dark:bg-surface-2/40" :aria-label="$t('taskPage.status')">
          <ol class="grid grid-cols-4 gap-1.5">
            <li v-for="(s, i) in STEPS" :key="s" class="min-w-0">
              <div class="h-1.5 rounded-full" :class="i <= step ? (task.status === 'done' ? 'bg-emerald-500' : 'bg-brand-600') : 'bg-slate-200 dark:bg-surface-2'" />
              <p class="mt-1.5 truncate text-[11px] font-semibold sm:text-xs" :class="i === step ? 'text-slate-900 dark:text-white' : 'text-slate-400'" :aria-current="i === step ? 'step' : undefined">{{ $t(`assignTask.status_${s}`) }}</p>
            </li>
          </ol>

          <div v-if="task.status === 'done'" class="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-emerald-50 px-4 py-3 dark:bg-emerald-500/10">
            <p class="flex items-center gap-2 font-bold text-emerald-800 dark:text-emerald-200"><Icon name="checkCircle" class="h-5 w-5" />{{ $t('taskPage.doneTitle') }}</p>
            <button type="button" :disabled="busy" class="min-h-10 rounded-xl px-3 text-sm font-semibold text-emerald-800 hover:bg-emerald-100 disabled:opacity-50 dark:text-emerald-200 dark:hover:bg-emerald-500/20" @click="move('in_progress')">{{ $t('taskPage.reopen') }}</button>
          </div>
          <div v-else class="mt-5 flex flex-col gap-2 sm:flex-row">
            <button v-if="next" type="button" :disabled="busy" class="flex min-h-12 flex-1 items-center justify-center gap-2 rounded-2xl bg-brand-600 px-5 font-bold text-white shadow-sm transition hover:bg-brand-700 active:scale-[0.98] disabled:opacity-50" @click="move(next.status)">
              <Icon :name="next.icon" class="h-5 w-5" />{{ next.label }}
            </button>
            <button v-if="task.status !== 'in_progress'" type="button" :disabled="busy" class="min-h-12 rounded-2xl border border-hairline px-5 font-semibold text-slate-700 hover:bg-white disabled:opacity-50 dark:text-slate-200 dark:hover:bg-surface" @click="move('done')">
              {{ $t('taskPage.done') }}
            </button>
          </div>
          <p v-if="flash" role="status" class="mt-3 flex items-center gap-1.5 text-sm font-medium text-emerald-700 dark:text-emerald-300"><Icon name="check" class="h-4 w-4" />{{ flash }}</p>
          <p v-if="error" role="alert" class="mt-3 text-sm text-red-600 dark:text-red-400">{{ error }}</p>
        </section>

        <!-- A word back -->
        <section class="border-t border-hairline p-5 sm:p-7">
          <label for="task-note" class="text-sm font-semibold text-slate-800 dark:text-slate-100">{{ $t('taskPage.noteLabel', { founder: task.founder_name }) }}</label>
          <textarea id="task-note" v-model="note" rows="3" maxlength="1000" :placeholder="$t('taskPage.notePlaceholder')" class="zx-input mt-2 w-full resize-y py-2 text-sm" @input="noteSent = false" />
          <div class="mt-2 flex justify-end">
            <button type="button" :disabled="busy || note === (task.note || '')" class="flex min-h-10 items-center gap-1.5 rounded-xl bg-slate-900 px-4 text-sm font-semibold text-white disabled:opacity-40 dark:bg-white dark:text-slate-900" @click="sendNote">
              <Icon :name="noteSent ? 'check' : 'send'" class="h-4 w-4" />{{ noteSent ? $t('taskPage.noteSent') : $t('taskPage.sendNote') }}
            </button>
          </div>
        </section>
      </article>

      <footer v-if="state === 'ready'" class="mt-4 flex flex-wrap items-center justify-between gap-2 px-1 text-xs text-slate-400">
        <span>{{ $t('taskPage.powered') }}</span>
        <span v-if="task.letters_off" class="text-slate-500">{{ $t('taskPage.lettersOffDone') }}</span>
        <button v-else type="button" :disabled="busy" class="underline underline-offset-2 hover:text-slate-600 disabled:opacity-50 dark:hover:text-slate-200" @click="lettersOff">{{ $t('taskPage.lettersOff') }}</button>
      </footer>
    </div>
  </div>
</template>
