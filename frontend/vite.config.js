import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

import { DESCRIPTION, DISALLOW, HOME_TITLE, PUBLIC_PAGES, SITE_URL } from './site.config.js'

// Serve the dev server over HTTPS with the same locally-trusted cert nginx uses
// for zinvest.loc, when it's present. The backend redirects HTTP→HTTPS and sets a
// `Secure` refresh cookie, which a plain-http origin (http://zinvest.loc:5173)
// can't store — so the SPA has to run on https too. Falls back to http on a
// machine without the cert (e.g. CI), where the plain-SQLite backend is fine.
const certPath = fileURLToPath(new URL('../deploy/nginx/certs/zinvest.loc.pem', import.meta.url))
const keyPath = fileURLToPath(new URL('../deploy/nginx/certs/zinvest.loc-key.pem', import.meta.url))
const https =
  !process.env.ZINVEST_HTTP && existsSync(certPath) && existsSync(keyPath)
    ? { cert: readFileSync(certPath), key: readFileSync(keyPath) }
    : undefined

const escapeHtml = (text) => text.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')

/**
 * Search engines, from site.config.js: the site address and description go into
 * index.html (%SITE_URL%, %DESCRIPTION%), robots.txt and sitemap.xml are written
 * at build time, and every public page gets its own copy of the HTML with its
 * own canonical link, og:url and title. Vercel serves those files before the
 * SPA rewrite, so /register is indexed as /register, not as a copy of /.
 */
function seo() {
  let outDir = 'dist'
  const forPage = (html, page) => {
    const url = SITE_URL + page.path
    const title = escapeHtml(page.title)
    return html
      .replace(/(<link rel="canonical" href=")[^"]*(")/, `$1${url}$2`)
      .replace(/(<meta property="og:url" content=")[^"]*(")/, `$1${url}$2`)
      .replace(/<title>[^<]*<\/title>/, `<title>${title}</title>`)
      .replace(/(<meta property="og:title" content=")[^"]*(")/, `$1${title}$2`)
      .replace(/(<meta name="twitter:title" content=")[^"]*(")/, `$1${title}$2`)
  }
  return {
    name: 'zinvest-seo',
    configResolved(config) {
      outDir = config.build.outDir
    },
    transformIndexHtml(html) {
      return html.replaceAll('%SITE_URL%', SITE_URL).replaceAll('%DESCRIPTION%', escapeHtml(DESCRIPTION)).replaceAll('%HOME_TITLE%', escapeHtml(HOME_TITLE))
    },
    generateBundle() {
      const today = new Date().toISOString().slice(0, 10)
      const robots = ['User-agent: *', 'Allow: /', '# The signed-in app, the admin and the API are not for search results.',
        ...DISALLOW.map((path) => `Disallow: ${path}`), '', `Sitemap: ${SITE_URL}/sitemap.xml`, '']
      const urls = PUBLIC_PAGES.map((page) => [
        '  <url>', `    <loc>${SITE_URL}${page.path}</loc>`, `    <lastmod>${today}</lastmod>`,
        `    <changefreq>${page.changefreq}</changefreq>`, `    <priority>${page.priority}</priority>`, '  </url>',
      ].join('\n'))
      const sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">', ...urls, '</urlset>', ''].join('\n')
      this.emitFile({ type: 'asset', fileName: 'robots.txt', source: robots.join('\n') })
      this.emitFile({ type: 'asset', fileName: 'sitemap.xml', source: sitemap })
    },
    writeBundle() {
      const html = readFileSync(join(outDir, 'index.html'), 'utf8')
      for (const page of PUBLIC_PAGES) {
        if (page.path === '/') continue
        const dir = join(outDir, page.path)
        mkdirSync(dir, { recursive: true })
        writeFileSync(join(dir, 'index.html'), forPage(html, page))
      }
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue({
      // MathLive ships <math-field> as a native custom element; tell the Vue
      // compiler to leave it alone instead of trying to resolve a component.
      template: { compilerOptions: { isCustomElement: (tag) => tag === 'math-field' } },
    }),
    tailwindcss(),
    seo(),
  ],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    https,

    allowedHosts: ['zinvest.loc'],
    // Same-origin illusion in dev so the SameSite=Strict refresh cookie works
    // without CORS: the SPA and /api are served from the same Vite origin. The
    // target MUST be https — http://zinvest.loc 301-redirects to https, and the
    // browser follows that cross-origin redirect (turning the refresh POST into a
    // GET), which fails CORS and returns 405. `secure: false` skips cert
    // verification for this known local host so a cert regen can't break dev.
    proxy: {
      '/api': { target: process.env.ZINVEST_API_TARGET || (https ? 'https://zinvest.loc' : 'http://127.0.0.1:8000'), changeOrigin: true, secure: false },
      // Uploaded avatars. Django serves these only while DEBUG is on; in
      // production Nginx maps /media/ straight to the volume.
      '/media': { target: process.env.ZINVEST_API_TARGET || (https ? 'https://zinvest.loc' : 'http://127.0.0.1:8000'), changeOrigin: true, secure: false },
    },
  },
})
