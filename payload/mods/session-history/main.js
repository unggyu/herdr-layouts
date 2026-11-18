import { View, div } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { exec, appHome, props, focused, panes, theme, checking, closeOverlay } from "herdr";
export default class History extends View {
 init(_p,cx) {
  this.candidates=null;this.expanded={};this.rows=[];this.selected={};this.results={};this.busy=false;this.all=false;this.query="";
  this.target=props()?.terminal;this.tab=focused()?.tab??panes().find(p=>p.focused)?.tab;this.all=!this.tab;
  this.handle=cx.focus_handle();this.handle.focus();
  if(!checking()) cx.spawn(async(cx)=>{await this.load();cx.notify();});
 }
 async api(action,entry,candidate) {
  const r=await exec("__HERDR_PYTHON__",["-I",`${appHome()}/mods/session-restore/history.py`,action,...(entry?["--entry",entry]:[]),...(candidate?["--candidate",candidate]:[])],{timeout:180000});
  const data=JSON.parse(r.stdout);if(data.error)throw new Error(data.error);return data;
 }
 async load(){try{this.rows=await this.api("list");}catch(e){this.error=String(e);}}
 button(text,fn,t){return div().px(10).py(6).border(1).border_color(t.border).bg(t.surface).child(text).on_click(fn);}
 render(cx){
  const t=theme();const current=panes().filter(p=>this.all||!this.tab||p.tab===this.tab);const ids=new Set(current.map(p=>p.terminal));
  const seen=new Set();const rows=this.rows.filter(r=>(this.target?r.terminal===this.target:this.all||ids.has(r.terminal))&&(`${r.title} ${r.record?.cwd??""}`).toLowerCase().includes(this.query.toLowerCase())).filter(r=>{const prior=seen.has(r.terminal);seen.add(r.terminal);return !prior||this.expanded[r.terminal];});
  return v_flex().size_full().p(14).gap(10).bg(t.surface).text_color(t.foreground).track_focus(this.handle)
   .on_key_down((e,cx)=>{if(e.key==="escape")closeOverlay(props().overlay);else if(e.key==="backspace")this.query=this.query.slice(0,-1);else if(e.key?.length===1&&!e.modifiers?.control)this.query+=e.key;cx.notify();})
   .child(div().text_size(18).child("대화 이력·복구 — 항상 --yolo"))
   .child(h_flex().gap(8).child(this.button(this.all?"전체 탭":"현재 탭",(e,cx)=>{this.target=null;this.all=!this.all;cx.notify();},t))
    .child(this.button("새로고침",(e,cx)=>cx.spawn(async(cx)=>{await this.load();cx.notify();}),t))
    .child(this.button(this.busy?"복구 중…":"선택한 항목 복구",(e,cx)=>{if(this.busy)return;this.busy=true;cx.spawn(async(cx)=>{for(const id of Object.values(this.selected)){try{const r=await this.api("restore",id);this.results[id]=r.status==="restored"?"재개 확인":r.error;}catch(e){this.results[id]=String(e);}cx.notify();}this.busy=false;cx.notify();});},t)))
   .child(div().child(`검색: ${this.query||"제목 또는 폴더를 입력하세요 (Backspace로 지우기)"}`))
   .child(div().child(this.error??`${this.rows.length}건 / 표시 ${rows.length}건 · 빈 PowerShell pane에서 복구합니다. 기록이 없는 ID는 이전 기록을 선택하세요.`))
   .child(v_flex().flex_1().min_h(0).overflow_y_scrollbar().gap(5).children(rows.map(r=>v_flex().p(8).border(1).border_color(t.border)
    .bg(t.surface)
    .on_click((e,cx)=>{if(!this.busy){if(this.selected[r.terminal]===r.id)delete this.selected[r.terminal];else this.selected[r.terminal]=r.id;cx.notify();}})
    .child(div().child(`${this.selected[r.terminal]===r.id?"☑":"☐"} ${r.terminal} · ${r.title}`))
    .child(div().text_size(12).child(`${new Date(r.stamp*1000).toLocaleString()} · ${r.record?.cwd??"ID 수집 대기"} · ${r.record?.session_id?.slice(0,8)??"ID 미확인"}`))
    .child(div().text_size(12).child(this.results[r.id]??r.record?.evidence??"제목 기록"))
    .child(h_flex().gap(8)
      .child(this.button(this.expanded[r.terminal]?"이력 접기":"이전 기록 보기",(e,cx)=>{cx.stop_propagation();this.expanded[r.terminal]=!this.expanded[r.terminal];cx.notify();},t))
      .child(this.button("이 항목 복구",(e,cx)=>{cx.stop_propagation();if(this.busy)return;this.busy=true;cx.spawn(async(cx)=>{try{const v=await this.api("restore",r.id);this.results[r.id]=v.status==="restored"?"재개 확인":v.error;}catch(e){this.results[r.id]=String(e);}this.busy=false;cx.notify();});},t))
      .child(this.button("명령 복사",(e,cx)=>{cx.stop_propagation();cx.spawn(async(cx)=>{try{const v=await this.api("command",r.id);cx.write_to_clipboard(v.command);this.results[r.id]="명령 복사됨";}catch(e){this.results[r.id]=String(e);}cx.notify();});},t))
      .child(this.button("같은 폴더 대화 찾기",(e,cx)=>{cx.stop_propagation();if(this.busy)return;this.busy=true;cx.spawn(async(cx)=>{try{const v=await this.api("candidates",r.id);this.candidates={entry:r.id,rows:v.candidates};}catch(e){this.results[r.id]=String(e);}this.busy=false;cx.notify();});},t))))))
   .when(Boolean(this.candidates),el=>el.child(v_flex().max_h(180).overflow_y_scrollbar().children((this.candidates?.rows??[]).map(c=>this.button(`${c.title} · ${c.id.slice(0,8)}`,(e,cx)=>{if(this.busy)return;this.busy=true;cx.spawn(async(cx)=>{try{await this.api("candidates",this.candidates.entry,c.id);this.candidates=null;await this.load();}catch(e){this.error=String(e);}this.busy=false;cx.notify();});},t)))))
   .child(this.button("닫기",()=>closeOverlay(props().overlay),t));
 }
}
