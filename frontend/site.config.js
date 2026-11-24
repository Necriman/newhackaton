// The site's public address and its pages for search engines: the one source
// for canonical links, Open Graph, the sitemap and robots.txt (see the `seo`
// plugin in vite.config.js). Override with VITE_SITE_URL, without a trailing
// slash. Never derive it from VERCEL_URL or the request host: every deployment
// would then call itself the original.
export const SITE_URL = (process.env.VITE_SITE_URL || 'https://zinvest.uz').replace(/\/+$/, '')

// One description everywhere: meta description, Open Graph, Twitter, JSON-LD.
export const DESCRIPTION =
  'Финансовая грамотность простым языком: короткие уроки, тесты, практика и ИИ-наставник. На русском, узбекском и английском.'

export const HOME_TITLE = 'Zinvest — финансовая грамотность простым языком'

// Public pages that belong in search results. Each gets its own copy of
// index.html with its own canonical and title; Vercel serves that file before
// the SPA rewrite. The signed-in app, sign-in, the API stay out (robots.txt).
// Titles match what the app sets in the tab (router/titles.js, legal docs).
export const PUBLIC_PAGES = [
  { path: '/', title: HOME_TITLE, changefreq: 'weekly', priority: '1.0' },
  { path: '/register', title: 'Регистрация · Zinvest', changefreq: 'monthly', priority: '0.8' },
  { path: '/legal/privacy', title: 'Политика конфиденциальности · Zinvest', changefreq: 'yearly', priority: '0.3' },
  { path: '/legal/terms', title: 'Условия использования · Zinvest', changefreq: 'yearly', priority: '0.3' },
  { path: '/legal/cookies', title: 'Политика cookie · Zinvest', changefreq: 'yearly', priority: '0.3' },
  { path: '/legal/refund', title: 'Политика возврата · Zinvest', changefreq: 'yearly', priority: '0.3' },
  { path: '/legal/licenses', title: 'Лицензии и авторство · Zinvest', changefreq: 'yearly', priority: '0.3' },
]

// Kept out of search results: the app, the admin, the API and pages that only
// make sense signed in. (Same rules robots.txt had before it was generated.)
export const DISALLOW = ['/app', '/admin-panel', '/admin/', '/api/', '/learn/', '/notes/', '/onboarding', '/task/']
