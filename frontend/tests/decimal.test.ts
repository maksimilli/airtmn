import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseDecimal} from '../src/decimal.ts';

test('comma and dot decimals, leading separators and trailing separators',()=>{
 for (const [text,expected] of [['0,5',.5],['0.5',.5],['.25',.25],[',25',.25],['1.',1],['1,',1],['0',0],[' 2,75 ',2.75]] as const)
  assert.equal(parseDecimal(text),expected);
});
test('reject empty, negative, malformed and nonfinite input',()=>{
 for (const text of ['', ' ', '-1', '1,2.3', 'NaN', 'Infinity', 'abc', '9'.repeat(400)])
  assert.throws(()=>parseDecimal(text));
});
