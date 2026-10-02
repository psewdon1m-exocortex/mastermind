import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {transform} from 'esbuild';

const css=await readFile(new URL('../styles.css',import.meta.url),'utf8');
const source=css.replace(/\/\*[\s\S]*?\*\//g,'');
const parsed=await transform(css,{loader:'css'});
assert.deepEqual(parsed.warnings,[],'Plugin CSS must parse without warnings');
for(const [,selectors] of source.matchAll(/([^{}]+)\{/g)){
  for(const selector of selectors.split(','))assert.match(selector.trim(),/^\.mastermind-[\w-]+/,
    'Every selector must be scoped to a Bridge component');
}
assert.doesNotMatch(source,/--mm-[\w-]+\s*:/,'Local public-token defaults mask inherited snippet overrides');
assert.doesNotMatch(source,/!important|#[\da-f]{3,8}\b|\b(?:rgb|hsl)a?\(/i,'No fixed palette or forced specificity');
for(const file of ['commands.ts','related.ts','resources.ts']){
  const ts=await readFile(new URL('../src/'+file,import.meta.url),'utf8');
  assert.doesNotMatch(ts,/\.style\.|\.style\s*=|setAttribute\(["']style/,'UI geometry belongs in themeable CSS');
}
console.log('PASS Bridge CSS scoping, inherited public tokens, palette and inline-style guards');
