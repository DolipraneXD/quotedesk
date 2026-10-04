// Fails if en.json and zh.json don't have exactly the same keys, or if a literal
// t('key') in the source is missing from them. Dynamic keys (t(`status.${s}`)) are
// covered by the catalogs being identical in shape.
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

const dir = new URL('../src/', import.meta.url).pathname
const flatten = (obj, prefix = '') =>
  Object.entries(obj).flatMap(([k, v]) =>
    typeof v === 'object' ? flatten(v, `${prefix}${k}.`) : [`${prefix}${k}`],
  )
const en = new Set(flatten(JSON.parse(readFileSync(join(dir, 'i18n/en.json'), 'utf8'))))
const zh = new Set(flatten(JSON.parse(readFileSync(join(dir, 'i18n/zh.json'), 'utf8'))))

const problems = []
for (const k of en) if (!zh.has(k)) problems.push(`missing in zh.json: ${k}`)
for (const k of zh) if (!en.has(k)) problems.push(`missing in en.json: ${k}`)

const walk = (d) =>
  readdirSync(d).flatMap((f) => {
    const p = join(d, f)
    return statSync(p).isDirectory() ? walk(p) : /\.tsx?$/.test(p) ? [p] : []
  })
for (const file of walk(dir)) {
  for (const m of readFileSync(file, 'utf8').matchAll(/\bt\('([a-zA-Z_.]+)'/g)) {
    if (!en.has(m[1])) problems.push(`${file.replace(dir, '')}: unknown key ${m[1]}`)
  }
}
if (problems.length) {
  console.error(problems.join('\n'))
  process.exit(1)
}
console.log(`i18n ok: ${en.size} keys in en and zh`)
