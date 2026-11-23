import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const [project, python, helper] = process.argv.slice(2);
Object.assign(process.env, {LOCAL_AI_PROJECT:project, LOCAL_AI_EXECUTION_DIR:project+"/execution",
  LOCAL_AI_EXECUTION_PYTHON:python, LOCAL_AI_EXECUTION_HELPER:helper});
let tick;
globalThis.setInterval = fn => { tick=fn; return {unref(){}}; };
// Only the SDK schema builder is stubbed; exercise the shipped plugin and real RPC.
const schema = new Proxy(()=>schema, {get:()=>schema});
globalThis.testTool = Object.assign(value=>value, {schema});
const source = readFileSync(helper.replace(/execution\.py$/, "execution.mjs"), "utf8")
  .replace('import { tool } from "@opencode-ai/plugin";', "const tool=globalThis.testTool;");
const plugin = (await import("data:text/javascript;base64,"+Buffer.from(source).toString("base64"))).default;
const messages = new Map(), toasts=[], prompts=[], errors=[];
const client = {
  session:{
    status:async()=>({data:{}}),
    message:async({path})=>({data:messages.get(path.messageID)}),
    messages:async()=>({data:[{parts:[{type:"tool",tool:"local_ai_task",state:{status:"completed",
      input:{action:"output",job_id:job(4)},output:JSON.stringify({id:job(4),state:"completed",
        offset:0,next_offset:6,total_bytes:6,all_output_delivered:true,truncated:false})}}]}]}),
    promptAsync:async({body})=>{ prompts.push(body); messages.set(body.messageID,body); return {}; },
  },
  tui:{showToast:async({body})=>{toasts.push(body);return {};}},
  app:{log:async({body})=>{errors.push(body.message);}},
};
let hooks = await plugin({directory:project, client});
const context = {sessionID:"ses_test",metadata(){},async ask(){}};
const job = n => "job_"+String(n).repeat(32);
const output = (n, offset=0, limit=16384) => hooks.tool.local_ai_task.execute(
  {action:"output",job_id:job(n),offset,limit},context);
await hooks["chat.message"]({sessionID:"ses_test"},{parts:[{type:"text",text:"query t08"}]});
await output(0); // Already read and included in the conclusion.
await output(1,0,2);
await output(1,2); // Paginated output also counts once fully read.
await output(2); // A read failure result keeps its warning toast without another reply.
await hooks.tool.local_ai_task.execute({action:"status",job_id:job(3)},context);
// Recreate the plugin to verify deduplication survives chat restart.
hooks = await plugin({directory:project,client});
await hooks["chat.message"]({sessionID:"ses_test"},{parts:[{type:"text",text:"continue"}]});
for (let i=0;i<8;i++) await tick();
assert.deepEqual(errors,[]);
assert.equal(prompts.length,1,"Already-read tasks must never reach the model again");
assert.equal(toasts.length,6);
assert.ok(toasts.some(t=>t.message.includes(job(5))),"Unread automatic tasks still show one toast");
assert.equal(toasts.filter(t=>t.variant==="warning").length,1);
assert.ok(prompts[0].parts[0].text.includes(job(3)),"Unread output still triggers automatic continuation");
assert.ok(!prompts[0].parts[0].text.includes(job(0)));
console.log(JSON.stringify({toasts:toasts.length,prompts:prompts.length}));
