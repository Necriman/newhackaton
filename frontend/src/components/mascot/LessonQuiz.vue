<script setup>
/**
 * The check after a lesson. "Mark complete" opens it; reaching the pass mark
 * completes the lesson on the server (coins, streak day) and the page moves on
 * to the celebration. A miss marks which questions were wrong, never the right
 * answers: the way through is reading that part of the lesson again.
 */
import { computed, nextTick, ref, watch } from 'vue'

import BearMascot from './BearMascot.vue'
import BearSticker from './BearSticker.vue'
import Icon from '@/components/ui/Icon.vue'
import { submitLessonQuiz } from '@/api/lessons'

const props = defineProps({
  open: { type: Boolean, default: false },
  lessonId: { type: String, default: '' },
  quiz: { type: Object, default: null },
})
const emit = defineEmits(['close', 'passed'])

const phase = ref('intro') // intro | question | submitting | result
const index = ref(0)
const answers = ref({})
const result = ref(null)
const error = ref('')
const card = ref(null)

const questions = computed(() => props.quiz?.questions || [])
const question = computed(() => questions.value[index.value])
const isLast = computed(() => index.value === questions.value.length - 1)
const selected = computed({
  get: () => answers.value[question.value?.id] ?? null,
  set: (i) => { answers.value = { ...answers.value, [question.value.id]: i } },
})
const progress = computed(() =>
  phase.value === 'result' ? 100 : Math.round((100 * index.value) / Math.max(1, questions.value.length)),
)
const rows = computed(() =>
  (result.value?.results || []).map((r) => ({ ...r, prompt: questions.value.find((q) => q.id === r.id)?.prompt || '' })),
)

function reset() {
  phase.value = 'intro'
  index.value = 0
  answers.value = {}
  result.value = null
  error.value = ''
}
watch(() => props.open, async (open) => {
  if (!open) return
  reset()
  await nextTick()
  card.value?.focus()
})

function begin() {
  phase.value = 'question'
}
function prev() {
  if (index.value > 0) index.value -= 1
}
function next() {
  if (selected.value === null) return
  if (isLast.value) submit()
  else index.value += 1
}
async function submit() {
  phase.value = 'submitting'
  error.value = ''
  try {
    const payload = questions.value.map((q) => ({ question_id: q.id, choice_index: answers.value[q.id] }))
    const data = await submitLessonQuiz(props.lessonId, payload)
    if (data.passed) {
      emit('passed', data)
      return
    }
    result.value = data
    phase.value = 'result'
  } catch (e) {
    error.value = e?.response?.data?.detail || ''
    phase.value = 'question'
  }
}
function retry() {
  index.value = 0
  answers.value = {}
  result.value = null
  phase.value = 'question'
}
</script>

<template>
  <Teleport to="body">
    <Transition name="zq">
      <div v-if="open && quiz" class="fixed inset-0 z-[80] flex items-end justify-center bg-slate-900/45 p-3 backdrop-blur-[2px] sm:items-center sm:p-6" @keydown.esc="emit('close')" @click.self="emit('close')">
        <div ref="card" tabindex="-1" role="dialog" aria-modal="true" aria-labelledby="zq-title" class="zq-card relative flex max-h-[92vh] w-full max-w-xl flex-col overflow-hidden rounded-3xl bg-white shadow-2xl outline-none dark:bg-surface">
          <header class="flex items-center gap-3 border-b border-hairline px-4 py-3">
            <p id="zq-title" class="shrink-0 text-sm font-bold text-brand-700 dark:text-brand-300">{{ $t('lessonQuiz.label') }}</p>
            <div class="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100 dark:bg-surface-2" role="progressbar" :aria-valuenow="progress" aria-valuemin="0" aria-valuemax="100" :aria-label="$t('lessonQuiz.label')">
              <div class="h-full rounded-full bg-brand-600 transition-[width] duration-500 ease-out" :style="{ width: progress + '%' }" />
            </div>
            <button type="button" class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-surface-2" :aria-label="$t('lessonQuiz.close')" :title="$t('lessonQuiz.close')" @click="emit('close')">
              <Icon name="x" class="h-4 w-4" />
            </button>
          </header>

          <div class="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-6">
            <!-- What it is and what it takes -->
            <section v-if="phase === 'intro'" class="text-center">
              <div class="mx-auto h-44 w-44"><BearMascot mood="warmup" interactive :label="$t('mascot.tap')" /></div>
              <h2 class="mt-1 text-2xl font-extrabold text-slate-900 dark:text-white">{{ $t('lessonQuiz.title') }}</h2>
              <p class="mt-2 text-slate-600 dark:text-slate-300">{{ $t('lessonQuiz.intro', { n: quiz.total, pass: quiz.pass_mark }) }}</p>
              <p v-if="quiz.best !== null && quiz.best !== undefined" class="mt-2 text-sm text-slate-500">{{ $t('lessonQuiz.best', { c: quiz.best, n: quiz.total }) }}</p>
              <button type="button" class="mt-6 min-h-12 w-full rounded-2xl bg-brand-600 px-6 text-lg font-bold text-white shadow-sm transition hover:bg-brand-700" @click="begin">{{ $t('lessonQuiz.start') }}</button>
              <button type="button" class="mt-2 min-h-11 w-full rounded-2xl px-5 font-semibold text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-surface-2" @click="emit('close')">{{ $t('lessonQuiz.reread') }}</button>
            </section>

            <!-- One question at a time -->
            <section v-else-if="phase === 'question' && question" :key="question.id" class="zq-question">
              <p class="text-sm font-semibold text-brand-600">{{ $t('unitTest.question', { i: index + 1, n: questions.length }) }}</p>
              <h2 class="mt-1 text-lg font-bold leading-snug text-slate-900 sm:text-xl dark:text-white">{{ question.prompt }}</h2>
              <fieldset class="mt-5 space-y-2.5">
                <legend class="sr-only">{{ question.prompt }}</legend>
                <label
                  v-for="(choice, i) in question.choices"
                  :key="i"
                  class="flex min-h-13 cursor-pointer items-center gap-3 rounded-2xl border-2 bg-white px-4 py-3 text-[15px] transition has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-brand-500 dark:bg-surface"
                  :class="selected === i ? 'border-brand-500 bg-brand-50/60 dark:bg-brand-500/10' : 'border-hairline hover:border-slate-300 dark:hover:border-slate-500'"
                >
                  <input v-model="selected" type="radio" class="sr-only" :value="i" :name="`lesson-quiz-${question.id}`" />
                  <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border text-sm font-bold" :class="selected === i ? 'border-brand-500 bg-brand-600 text-white' : 'border-slate-300 text-slate-500 dark:border-slate-600'">{{ i + 1 }}</span>
                  <span>{{ choice }}</span>
                </label>
              </fieldset>
              <p v-if="error" role="alert" class="mt-4 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">{{ error }}</p>
            </section>

            <div v-else-if="phase === 'submitting'" class="py-8 text-center" role="status">
              <BearSticker name="think" float class="mx-auto h-36 w-36" />
              <p class="mt-2 font-semibold text-slate-600 dark:text-slate-300">{{ $t('unitTest.checking') }}</p>
            </div>

            <!-- Not passed: which ones were wrong, not what is right -->
            <section v-else-if="phase === 'result' && result">
              <div class="text-center">
                <BearSticker name="confused" pop class="mx-auto h-32 w-32" />
                <h2 class="mt-1 text-2xl font-extrabold text-slate-900 dark:text-white">{{ $t('lessonQuiz.failedTitle') }}</h2>
                <p class="mt-1 text-lg font-semibold text-amber-600">{{ $t('lessonQuiz.score', { c: result.correct, n: result.total, pass: result.pass_mark }) }}</p>
                <p class="mt-2 text-slate-600 dark:text-slate-300">{{ $t('lessonQuiz.failedText') }}</p>
              </div>
              <ol class="mt-5 space-y-2">
                <li v-for="(row, i) in rows" :key="row.id" class="flex items-start gap-3 rounded-2xl border border-hairline px-4 py-3">
                  <span class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-white" :class="row.correct ? 'bg-emerald-500' : 'bg-amber-500'">
                    <Icon :name="row.correct ? 'check' : 'x'" class="h-3.5 w-3.5" />
                  </span>
                  <div class="min-w-0">
                    <p class="font-semibold text-slate-900 dark:text-white">{{ i + 1 }}. {{ row.prompt }}</p>
                    <p class="mt-0.5 text-sm font-medium" :class="row.correct ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'">
                      {{ row.correct ? $t('lessonQuiz.right') : $t('lessonQuiz.wrong') }}
                    </p>
                    <p v-if="row.explanation" class="mt-0.5 text-sm text-slate-500">{{ row.explanation }}</p>
                  </div>
                </li>
              </ol>
            </section>
          </div>

          <footer v-if="phase === 'question'" class="flex items-center justify-between gap-3 border-t border-hairline px-5 py-3 sm:px-6">
            <button type="button" :disabled="index === 0" class="min-h-11 rounded-2xl px-4 font-semibold text-slate-600 hover:bg-slate-100 disabled:invisible dark:text-slate-300 dark:hover:bg-surface-2" @click="prev">{{ $t('unitTest.prev') }}</button>
            <button type="button" :disabled="selected === null" class="min-h-11 rounded-2xl bg-brand-600 px-6 font-bold text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-40" @click="next">{{ isLast ? $t('lessonQuiz.finish') : $t('unitTest.next') }}</button>
          </footer>
          <footer v-else-if="phase === 'result'" class="flex flex-col gap-2 border-t border-hairline px-5 py-3 sm:flex-row sm:justify-end sm:px-6">
            <button type="button" class="min-h-11 rounded-2xl border border-hairline px-5 font-semibold hover:bg-slate-50 dark:hover:bg-surface-2" @click="emit('close')">{{ $t('lessonQuiz.reread') }}</button>
            <button type="button" class="min-h-11 rounded-2xl bg-brand-600 px-6 font-bold text-white shadow-sm hover:bg-brand-700" @click="retry">{{ $t('lessonQuiz.retry') }}</button>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.min-h-13 { min-height: 3.25rem; }
.zq-question { animation: zq-in 0.25s ease both; }
@keyframes zq-in { from { opacity: 0; transform: translateX(14px); } to { opacity: 1; transform: none; } }
.zq-enter-active, .zq-leave-active { transition: opacity 0.2s ease; }
.zq-enter-active .zq-card { transition: transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1); }
.zq-enter-from, .zq-leave-to { opacity: 0; }
.zq-enter-from .zq-card { transform: translateY(32px) scale(0.97); }
@media (prefers-reduced-motion: reduce) {
  .zq-question { animation: none; }
  .zq-enter-active .zq-card { transition: none; }
}
</style>
