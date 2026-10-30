"use strict";
const $ = id => document.getElementById(id);
let csrf = "", currentId = null, timer = null, currentJob = null, activeFile = null;
const names = {"system-analysis.md":"Системный анализ", "acceptance-tests.md":"Сценарии проверки", "traceability.csv":"Связи требований и тестов", "quality-report.json":"Отчет о проверке", "requirements.md":"Исходные требования", "analysis.json":"Анализ · JSON", "design.json":"Проект · JSON", "answers.json":"Ответы на вопросы", "failure-report.json":"Отчет об ошибке", "cancellation-report.json":"Отчет об отмене", "pending-report.json":"Метрики анализа", "openapi.json":"OpenAPI", "data-model.json":"Модель данных", "screens.json":"Экраны", "events.json":"События", "permissions.json":"Права", "assumptions-and-questions.md":"Допущения и вопросы"};
function notice(message, error=false) { $("notice").textContent=message; $("notice").hidden=!message; $("notice").classList.toggle("error",error); }
async function api(path, body) {
  const options = body===undefined ? {} : {method:"POST",headers:{"Content-Type":"application/json","X-Pipeline-Token":csrf},body:JSON.stringify(body)};
  const response = await fetch(path,options); let data;
  try { data=await response.json(); } catch { throw new Error("Сервер не ответил. Проверьте, запущено ли приложение"); }
  if (!response.ok) throw new Error(data.error || "Не удалось выполнить действие");
  return data;
}
function setBusy(busy) { for(const id of ["generate","demo","example","requirements","base-url","model","api-key"]) $(id).disabled=busy; }
function updateCount() { $("char-count").textContent=$("requirements").value.length.toLocaleString("ru-RU")+" / 20 000"; }
$("requirements").addEventListener("input",updateCount);
$("base-url").addEventListener("input",()=>{$("connection-label").textContent=$("base-url").value.trim()?"адрес указан, доступ еще не проверен":"нужен адрес API";});
async function start(demo) {
  notice("");
  if(!demo) {
    if($("requirements").value.trim().length<30) return notice("Добавьте описание задачи: хотя бы 30 символов",true);
    if(!$("base-url").value.trim()) { $("settings").open=true; $("base-url").focus(); return notice("Для генерации нужен адрес API Qwen. Пока можно посмотреть готовый пример",true); }
  }
  setBusy(true);
  try {
    const data=await api(demo?"/api/demo":"/api/runs",demo?{}:{requirements:$("requirements").value,config:{base_url:$("base-url").value,model:$("model").value,api_key:$("api-key").value}});
    currentId=data.id; activeFile=null; currentJob=null; sessionStorage.setItem("pipeline-run",currentId);
    $("api-key").value=""; $("questions-panel").hidden=true; $("results").hidden=true; $("run-panel").hidden=false; await poll();
  } catch(error) { notice(error.message,true);setBusy(false); }
}
$("generate").onclick=()=>start(false); $("demo").onclick=()=>start(true);
function render(job) {
  currentJob=job;
  $("run-panel").hidden=false;
  $("run-kind").textContent=job.demo?"ГОТОВЫЙ ПРИМЕР · БЕЗ QWEN":"ХОД ГЕНЕРАЦИИ ЧЕРЕЗ QWEN";
  const states={running:"Работаем над документами…",awaiting_answers:"Есть вопросы к требованиям",complete:"Документы подготовлены",failed:"Запуск остановлен с ошибкой",cancelled:"Запуск отменен"};
  $("run-status").textContent=states[job.status]||job.status;
  const busy=["running","awaiting_answers"].includes(job.status);setBusy(busy);$("cancel").hidden=!busy;
  $("events").replaceChildren(...job.events.map(event=>{const row=document.createElement("div");row.className="event";const time=document.createElement("time");time.textContent=new Date(event.time).toLocaleTimeString("ru-RU");row.append(time,document.createTextNode(event.text));return row;}));
  $("events").scrollTop=$("events").scrollHeight;
  const order=["analysis","questions","design","validation"];
  for(const li of document.querySelectorAll(".steps li")){const idx=order.indexOf(li.dataset.step), stage=order.indexOf(job.stage);li.classList.toggle("active",busy && idx===stage);li.classList.toggle("done",job.status==="complete" || stage>idx);}
  if(job.demo) notice("Это заранее подготовленный учебный пример. Введенный текст не анализировался, Qwen не вызывалась.");
  if(job.status==="failed") notice(job.error,true);
  if(job.status==="cancelled") notice("Запуск отменен. Уже отправленный запрос к API может завершиться и расходовать токены.");
  if(job.status==="awaiting_answers") {
    if($("questions-panel").dataset.run!==job.id) {
      $("questions-panel").dataset.run=job.id; $("assumptions").checked=false;
      $("questions").replaceChildren(...job.analysis.questions.map(q=>{const box=document.createElement("div");box.className="question";const label=document.createElement("label");label.htmlFor=q.id;label.textContent=q.question;const impact=document.createElement("p");impact.textContent="Почему важно: "+q.impact;const assumption=document.createElement("p");assumption.textContent="Без ответа: "+q.default_assumption;const input=document.createElement("textarea");input.id=q.id;input.maxLength=5000;input.dataset.question=q.id;input.placeholder="Ваш ответ или оставьте пустым для допущения";box.append(label,impact,assumption,input);return box;}));
    }
    $("questions-panel").hidden=false;
  } else $("questions-panel").hidden=true;
  if(job.files.length) showResults(job);
}
async function poll() {
  clearTimeout(timer);
  try { const job=await api("/api/runs/"+currentId);render(job);if(job.status==="running" || (job.status==="cancelled" && job.report===null)) timer=setTimeout(poll,1000); }
  catch(error) { notice(error.message,true);setBusy(false); }
}
$("continue").onclick=async()=>{
  const answers={};for(const input of $("questions").querySelectorAll("textarea")) answers[input.dataset.question]=input.value;
  $("continue").disabled=true;
  try { await api(`/api/runs/${currentId}/continue`,{answers,accept_assumptions:$("assumptions").checked});notice("");await poll(); }
  catch(error){notice(error.message,true);} finally {$("continue").disabled=false;}
};
$("cancel").onclick=async()=>{try{await api(`/api/runs/${currentId}/cancel`,{});await poll();}catch(error){notice(error.message,true);}};
function metric(value,label) { const box=document.createElement("div");box.className="metric";const strong=document.createElement("strong");strong.textContent=value;const span=document.createElement("span");span.textContent=label;box.append(strong,span);return box; }
function showResults(job) {
  $("results").hidden=false;$("result-kind").textContent=job.demo?"УЧЕБНЫЙ ПРИМЕР · ЗАРАНЕЕ ПОДГОТОВЛЕН":"РЕЗУЛЬТАТ ЗАПУСКА";
  $("results").querySelector("h2").textContent=job.status==="failed"?"Сохранен отчет об ошибке":job.status==="cancelled"?"Сохранен отчет об отмене":job.status==="awaiting_answers"?"Анализ готов · ожидаются ответы":"Документы готовы";
  const m=job.report.metrics;
  $("metrics").replaceChildren(metric(job.analysis?.functional_requirements.length ?? "—","требований выделено"),metric(job.design?.test_scenarios.length ?? "—","сценариев описано · не выполнено"),metric(m.model_calls,"обращений к модели"),metric(m.input_tokens!==null && m.output_tokens!==null?(m.input_tokens+m.output_tokens).toLocaleString("ru-RU"):"нет данных","токенов · по данным API"));
  $("download-all").href=`/api/runs/${job.id}/archive`;
  const sorted=[...job.files].sort((a,b)=>Object.keys(names).indexOf(a)-Object.keys(names).indexOf(b));
  $("file-list").replaceChildren(...sorted.map(name=>{const button=document.createElement("button");button.type="button";button.textContent=names[name]||name;button.dataset.file=name;button.classList.toggle("selected",name===activeFile);button.onclick=()=>preview(name);return button;}));
  if(!activeFile) preview(sorted[0]);
}
async function preview(name) {
  activeFile=name;const runId=currentId;
  $("preview-title").textContent=names[name]||name;$("preview").textContent="Загружаем…";$("download-file").href=`/api/runs/${runId}/files/${name}`;
  for(const button of $("file-list").querySelectorAll("button"))button.classList.toggle("selected",button.dataset.file===name);
  try {const data=await api(`/api/runs/${runId}/files/${name}?preview=1`);if(activeFile===name && runId===currentId)$("preview").textContent=data.content;}catch(error){notice(error.message,true);}
}
async function init() {
  try { const config=await api("/api/config");csrf=config.csrf_token;$("base-url").value=config.base_url;$("model").value=config.model;
    if(config.has_key)$("api-key").placeholder="Используется ключ из настроек сервера";
    $("base-url").dispatchEvent(new Event("input"));
    $("example").onclick=()=>{$("requirements").value=config.example_requirements;updateCount();};
    const saved=new URLSearchParams(window.location.search).get("run") || sessionStorage.getItem("pipeline-run");
    if(saved && /^[a-f0-9]{32}$/.test(saved)){currentId=saved;sessionStorage.setItem("pipeline-run",saved);await poll();}
  }catch(error){notice(error.message,true);}
}
init();
