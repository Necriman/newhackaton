// Units + the Duolingo-style study-plan node graph.
import http from '@/api/http'

export function listUnits() {
  return http.get('/learning/units').then((r) => r.data)
}

export function getStudyPlan(unitId) {
  return http.get(`/learning/units/${unitId}/study-plan`).then((r) => r.data)
}

/** Every unit's nodes in one payload — the map scrolls end to end, no tab swapping. */
export function getFullStudyPlan() {
  return http.get('/learning/study-plan').then((r) => r.data)
}

/** The catalogue: all lessons grouped by unit; `closed` ones wait for the lesson before. */
export function listLessons() {
  return http.get('/learning/lessons').then((r) => r.data)
}

export function startUnitTest(unitId) {
  return http.post(`/learning/units/${unitId}/test/start`, {}).then((r) => r.data)
}

export function submitUnitTest(unitId, answers) {
  return http.post(`/learning/units/${unitId}/test/submit`, { answers }).then((r) => r.data)
}
