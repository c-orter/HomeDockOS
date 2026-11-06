import{n as e}from"./hdos_COiEfhsAQcgkqpV1LRHhj.js";import{$n as t,E as n,Ht as r,J as i,Lt as a,On as o,Yt as s,Zn as c,_ as l,b as u,bt as d,ct as ee,er as f,et as p,fn as te,ft as m,g as h,gt as g,it as _,k as v,mt as y,o as b,qt as x,tr as S,tt as C,u as w,v as T,vn as E,w as D,wn as O,wt as k,xn as ne,xt as A,y as j}from"./hdos_B508z3v_JfpK2nzgMijjB.js";import{S as re,w as M}from"./hdos_DE8-hgalK6EZtvbrOukq9.js";import{_ as N,c as P,d as F,f as ie,g as I,h as L,l as R,m as z,o as ae,p as B,s as oe,u as V}from"./hdos_C3N1F8gp8vAqkpiWK8OOD.js";
/*
* Prism Window Manager (@prism-wm)
* Copyright (C) 2023-2026 Banshee Technologies S.L.
* Authors: Claudio González, Néstor González
* https://www.banshee.pro/
*
* Extracted from HomeDock OS: https://github.com/BansheeTech/HomeDockOS
*
* @license AGPL-3.0-or-later
*
* This program is free software: you can redistribute it and/or modify
* it under the terms of the GNU Affero General Public License as published by
* the Free Software Foundation, either version 3 of the License, or
* (at your option) any later version.
*
* This program is distributed in the hope that it will be useful,
* but WITHOUT ANY WARRANTY; without even the implied warranty of
* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
* GNU Affero General Public License for more details.
*
* You should have received a copy of the GNU Affero General Public License
* along with this program. If not, see <https://www.gnu.org/licenses/>.
*
* SPDX-License-Identifier: AGPL-3.0-or-later
*/
var H=.75,U=12e4,se=3e5,ce=5e3;function le(){let e=navigator.deviceMemory;return!e||e<2?4:e<=2?2:e<=4?4:e<=8?6:8}function ue(){let e=performance.memory;return e?e.usedJSHeapSize/e.jsHeapSizeLimit>H:!1}var W=class{constructor(e=()=>Date.now()){this.tracked=new Map,this.interval=null,this.now=e}onMinimize(e,t){this.tracked.set(e,{id:e,minimizedAt:this.now(),destroy:t}),this.start()}onRestore(e){this.tracked.delete(e),this.stopIfEmpty()}dispose(){this.tracked.clear(),this.stopIfEmpty()}expired(e){let t=this.now();return Array.from(this.tracked.values()).filter(n=>t-n.minimizedAt>e).sort((e,t)=>e.minimizedAt-t.minimizedAt)}cleanupOldest(e=1){let t=Array.from(this.tracked.values()).sort((e,t)=>e.minimizedAt-t.minimizedAt);for(let n=0;n<Math.min(e,t.length);n++)t[n].destroy(),this.tracked.delete(t[n].id);this.stopIfEmpty()}start(){this.interval||=setInterval(()=>this.tick(),ce)}tick(){let e=le(),t=this.tracked.size;if(ue()&&t>0){this.cleanupOldest(1);return}let n=this.expired(se);if(n.length>0){for(let e of n)e.destroy(),this.tracked.delete(e.id);this.stopIfEmpty()}else if(t>e){let n=this.expired(U),r=Math.min(n.length,t-e);for(let e=0;e<r;e++)n[e].destroy(),this.tracked.delete(n[e].id);this.stopIfEmpty()}}stopIfEmpty(){this.tracked.size===0&&this.interval&&(clearInterval(this.interval),this.interval=null)}},de={stiffness:600,damping:26},fe={stiffness:700,damping:16},pe=.004,me=64
/*
* Prism Window Manager (@prism-wm)
* Copyright (C) 2023-2026 Banshee Technologies S.L.
* Authors: Claudio González, Néstor González
* https://www.banshee.pro/
*
* Extracted from HomeDock OS: https://github.com/BansheeTech/HomeDockOS
*
* @license AGPL-3.0-or-later
*
* This program is free software: you can redistribute it and/or modify
* it under the terms of the GNU Affero General Public License as published by
* the Free Software Foundation, either version 3 of the License, or
* (at your option) any later version.
*
* This program is distributed in the hope that it will be useful,
* but WITHOUT ANY WARRANTY; without even the implied warranty of
* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
* GNU Affero General Public License for more details.
*
* You should have received a copy of the GNU Affero General Public License
* along with this program. If not, see <https://www.gnu.org/licenses/>.
*
* SPDX-License-Identifier: AGPL-3.0-or-later
*/
;function G(e,t,n,r){let{value:i,velocity:a}=e,o=Math.max(0,r);for(;o>0;){let e=Math.min(pe,o);a+=(n.stiffness*(t-i)-n.damping*a)*e,i+=a*e,o-=e}return{value:i,velocity:a}}var K={maxTilt:1.625,maxLean:5,maxTurn:3.25,tiltPerVelocity:1.5,leanPerVelocity:3,velocitySmoothingMs:45,perspective:1400,bounceVelocity:.6,wobbleSpring:de,bounceSpring:fe},he=.05,ge=.5,_e=.001,ve=.02,q=.001;function ye(e,t){return Math.max(-t,Math.min(t,e))}function J(e){return Math.round(e*1e3)/1e3}var be=class{constructor(e={}){this.rotateX={value:0,velocity:0},this.rotateY={value:0,velocity:0},this.rotateZ={value:0,velocity:0},this.scale={value:1,velocity:0},this.dragging=!1,this.pointer=null,this.pendingDx=0,this.pendingDy=0,this.vx=0,this.vy=0,this.lastTime=null,this.config={...K,...e}}dragStart(e,t){this.dragging=!0,this.pointer={x:e,y:t},this.pendingDx=0,this.pendingDy=0}dragMove(e,t){!this.dragging||!this.pointer?this.dragStart(e,t):(this.pendingDx+=e-this.pointer.x,this.pendingDy+=t-this.pointer.y,this.pointer={x:e,y:t})}dragEnd(){this.dragging=!1,this.pointer=null,this.pendingDx=0,this.pendingDy=0}bounce(e=1){this.scale={value:this.scale.value,velocity:this.scale.velocity+this.config.bounceVelocity*e}}get isDragging(){return this.dragging}get pose(){return{rotateX:this.rotateX.value,rotateY:this.rotateY.value,rotateZ:this.rotateZ.value,scale:this.scale.value}}get isAtRest(){return[this.rotateX,this.rotateY,this.rotateZ].every(e=>Math.abs(e.value)<he&&Math.abs(e.velocity)<ge)&&Math.abs(this.scale.value-1)<_e&&Math.abs(this.scale.velocity)<ve&&Math.abs(this.vx)<q&&Math.abs(this.vy)<q&&this.pendingDx===0&&this.pendingDy===0}step(e){let t=this.lastTime===null?0:Math.max(0,Math.min(me,e-this.lastTime));if(this.lastTime=e,t>0){let e=this.config,n=this.dragging?this.pendingDx/t:0,r=this.dragging?this.pendingDy/t:0;this.pendingDx=0,this.pendingDy=0;let i=1-Math.exp(-t/e.velocitySmoothingMs);this.vx+=(n-this.vx)*i,this.vy+=(r-this.vy)*i;let a=t/1e3;this.rotateZ=G(this.rotateZ,ye(this.vx*e.tiltPerVelocity,e.maxTilt),e.wobbleSpring,a),this.rotateY=G(this.rotateY,ye(this.vx*e.leanPerVelocity,e.maxTurn),e.wobbleSpring,a),this.rotateX=G(this.rotateX,ye(-this.vy*e.leanPerVelocity,e.maxLean),e.wobbleSpring,a),this.scale=G(this.scale,1,e.bounceSpring,a)}return!this.isAtRest||(this.reset(),!1)}get transform(){if(this.isAtRest)return null;let e=this.pose;return`perspective(${this.config.perspective}px) rotateX(${J(e.rotateX)}deg) rotateY(${J(e.rotateY)}deg) rotateZ(${J(e.rotateZ)}deg) scale(${J(e.scale)})`}reset(){this.rotateX={value:0,velocity:0},this.rotateY={value:0,velocity:0},this.rotateZ={value:0,velocity:0},this.scale={value:1,velocity:0},this.vx=0,this.vy=0,this.pendingDx=0,this.pendingDy=0,this.lastTime=null}},Y=`__pwm_dialog`,X=e({DEFAULT_LABELS:()=>xe,DEFAULT_MIN_HEIGHT:()=>300,DEFAULT_MIN_WIDTH:()=>400,DEFAULT_WINDOW_MOTION:()=>K,DIALOG_BOUNDARY_MARGIN:()=>16,EMPTY_CLASSES:()=>Se,KEEP_ON_SCREEN:()=>100,PRISM_CONTEXT:()=>Ce,PWM_BOUNCE_SPRING:()=>fe,PWM_CLOSE_ANIMATION_MS:()=>200,PWM_EXTERNAL_DIALOG_APP_ID:()=>Y,PWM_MINIMIZE_ANIMATION_MS:()=>200,PWM_OPEN_ANIMATION_MS:()=>200,PWM_UNSNAP_ANIMATION_MS:()=>200,PWM_WOBBLE_SPRING:()=>de,PrismDialog:()=>Ve,PrismWindow:()=>$,PrismWindowManager:()=>Le,RamManager:()=>W,SNAP_EDGE_THRESHOLD:()=>20,SNAP_VERTICAL_THRESHOLD:()=>2,UNSNAP_DRAG_THRESHOLD:()=>4,WindowManagerStore:()=>ae,WindowMotion:()=>be,centerDialog:()=>oe,clampDialogPosition:()=>P,clampPosition:()=>R,clampSize:()=>V,computeMinimizeTransform:()=>F,computeResize:()=>ie,computeSnapBounds:()=>B,computeSnapPreviewStyle:()=>z,computeUnsnapFlip:()=>L,computeWindowBounds:()=>I,createWindowManager:()=>Z,detectSnapEdge:()=>N,resolveCapabilities:()=>we,stepSpring:()=>G,useWindowManager:()=>Q})
/*
* Prism Window Manager (@prism-wm)
* Copyright (C) 2023-2026 Banshee Technologies S.L.
* Authors: Claudio González, Néstor González
* https://www.banshee.pro/
*
* Extracted from HomeDock OS: https://github.com/BansheeTech/HomeDockOS
*
* @license AGPL-3.0-or-later
*
* This program is free software: you can redistribute it and/or modify
* it under the terms of the GNU Affero General Public License as published by
* the Free Software Foundation, either version 3 of the License, or
* (at your option) any later version.
*
* This program is distributed in the hope that it will be useful,
* but WITHOUT ANY WARRANTY; without even the implied warranty of
* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
* GNU Affero General Public License for more details.
*
* You should have received a copy of the GNU Affero General Public License
* along with this program. If not, see <https://www.gnu.org/licenses/>.
*
* SPDX-License-Identifier: AGPL-3.0-or-later
*/
/*
* Prism Window Manager (@prism-wm)
* Copyright (C) 2023-2026 Banshee Technologies S.L.
* Authors: Claudio González, Néstor González
* https://www.banshee.pro/
*
* Extracted from HomeDock OS: https://github.com/BansheeTech/HomeDockOS
*
* @license AGPL-3.0-or-later
*
* This program is free software: you can redistribute it and/or modify
* it under the terms of the GNU Affero General Public License as published by
* the Free Software Foundation, either version 3 of the License, or
* (at your option) any later version.
*
* This program is distributed in the hope that it will be useful,
* but WITHOUT ANY WARRANTY; without even the implied warranty of
* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
* GNU Affero General Public License for more details.
*
* You should have received a copy of the GNU Affero General Public License
* along with this program. If not, see <https://www.gnu.org/licenses/>.
*
* SPDX-License-Identifier: AGPL-3.0-or-later
*/
;
/*
* Prism Window Manager (@prism-wm), Vue 3 adapter
* Copyright (C) 2023-2026 Banshee Technologies S.L.
* Authors: Claudio González, Néstor González
* https://www.banshee.pro/
*
* Extracted from HomeDock OS: https://github.com/BansheeTech/HomeDockOS
*
* @license AGPL-3.0-or-later
*
* This program is free software: you can redistribute it and/or modify
* it under the terms of the GNU Affero General Public License as published by
* the Free Software Foundation, either version 3 of the License, or
* (at your option) any later version.
*
* This program is distributed in the hope that it will be useful,
* but WITHOUT ANY WARRANTY; without even the implied warranty of
* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
* GNU Affero General Public License for more details.
*
* You should have received a copy of the GNU Affero General Public License
* along with this program. If not, see <https://www.gnu.org/licenses/>.
*
* SPDX-License-Identifier: AGPL-3.0-or-later
*/
function Z(e={}){return new ae(e)}function Q(e){let t=ne(e.getState()),n=e.subscribe(()=>{t.value=e.getState()});return m(n),t}
/*
* Prism Window Manager (@prism-wm), Vue 3 adapter
* Copyright (C) 2023-2026 Banshee Technologies S.L.
* Authors: Claudio González, Néstor González
* https://www.banshee.pro/
*
* Extracted from HomeDock OS: https://github.com/BansheeTech/HomeDockOS
*
* @license AGPL-3.0-or-later
*
* This program is free software: you can redistribute it and/or modify
* it under the terms of the GNU Affero General Public License as published by
* the Free Software Foundation, either version 3 of the License, or
* (at your option) any later version.
*
* This program is distributed in the hope that it will be useful,
* but WITHOUT ANY WARRANTY; without even the implied warranty of
* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
* GNU Affero General Public License for more details.
*
* You should have received a copy of the GNU Affero General Public License
* along with this program. If not, see <https://www.gnu.org/licenses/>.
*
* SPDX-License-Identifier: AGPL-3.0-or-later
*/
var xe={minimize:`Minimize`,maximize:`Maximize`,restore:`Restore`,close:`Close`},Se={manager:``,window:``,windowInactive:``,windowActive:``,titleBar:``,title:``,titleActive:``,iconContainer:``,iconContainerActive:``,control:``,closeControl:``,body:``,snapPreview:``,dialogFooter:``,dialogButton:``,dialogButtonPrimary:``,dialogButtonDanger:``},Ce=Symbol.for(`prism-wm.context.v1`);function we(e){return{resizable:e?.resizable!==!1,maximizable:e?.maximizable!==!1,minimizable:e?.minimizable!==!1,closeable:e?.closeable!==!1,minWidth:e?.minWidth,minHeight:e?.minHeight,maxWidth:e?.maxWidth,maxHeight:e?.maxHeight}}var Te=[`data-pwm-window`,`data-pwm-blocked`,`data-pwm-autoheight`],Ee=[`inert`],De={class:`pwm-window-controls`},Oe=[`title`],ke=[`title`],Ae=[`data-glyph`],je=[`title`],Me=[`inert`],Ne=[`data-pwm-slot`],Pe=[`onPointerdown`],Fe=300,$=v({__name:`PrismWindow`,props:{window:{},isActive:{type:Boolean},isBlocked:{type:Boolean,default:!1}},setup(e){let a=e,g=i(Ce);if(!g)throw Error(`PrismWindow must be used inside PrismWindowManager`);let _=g,v=h(()=>_.classes.value),x=E(null),C=E(!1),w=null;function D(e){if(_.store.setMeasuredHeight(a.window.id,e),C.value)return;let t=a.window.modality===`window`&&a.window.ownerId?_.store.getWindowById(a.window.ownerId):null,n=oe(a.window.width,e,{width:window.innerWidth,height:window.innerHeight},t);_.store.updateWindowPosition(a.window.id,n.x,n.y)}ee(()=>{a.window.autoHeight&&x.value&&(D(x.value.offsetHeight),typeof ResizeObserver<`u`&&(w=new ResizeObserver(()=>{let e=x.value?.offsetHeight;e&&D(e)}),w.observe(x.value)))}),m(()=>{w?.disconnect(),w=null});let O=[`n`,`s`,`e`,`w`,`ne`,`nw`,`se`,`sw`],ne=h(()=>_.appearance.value===`cupertino`?[`close`,`minimize`,`maximize`]:[`minimize`,`maximize`,`close`]),P=h(()=>{let e=we(_.resolveConfig(a.window));return a.window.kind===`dialog`?{...e,resizable:!1,minimizable:!1,maximizable:!1}:e}),R=h(()=>{let e=_.resolveComponent(a.window);return e?te(e):null}),z=E(!0),ae=setTimeout(()=>z.value=!1,200),B=E(!1),V=E(!1),H=E(null),U=null;r(()=>a.window.isMinimized,e=>{U&&clearTimeout(U);let t=_.store.getMinimizeTarget(a.window.id);H.value=t?F(I(a.window,ce(),_.taskbarHeight.value,_.isMobile.value&&a.window.kind!==`dialog`),t):null,B.value=e,V.value=!e,U=setTimeout(()=>{U=null,B.value=!1,V.value=!1,H.value=null},200)});let se=E(!0);r(()=>a.window.isMinimized,e=>{_.ram&&(e?_.ram.onMinimize(a.window.id,()=>se.value=!1):(_.ram.onRestore(a.window.id),se.value=!0))},{immediate:!0});let ce=()=>({width:typeof window<`u`?window.innerWidth:1920,height:typeof window<`u`?window.innerHeight:1080}),le=h(()=>({...Q.value?{"--pwm-unsnap-from":Q.value.transform,"--pwm-unsnap-from-content":Q.value.contentTransform}:{},...H.value?{"--pwm-minimize-to":H.value}:{}})),ue=h(()=>_.isMobile.value&&a.window.kind!==`dialog`?{top:`0`,left:`0`,width:`100vw`,height:`calc(100% - ${_.taskbarHeight.value}px)`,zIndex:a.window.zIndex}:a.window.isMaximized?{top:`0`,left:`0`,width:`100%`,height:`calc(100% - ${_.taskbarHeight.value}px)`,zIndex:a.window.zIndex}:{top:`${a.window.y}px`,left:`${a.window.x}px`,width:`${a.window.width}px`,height:a.window.autoHeight?void 0:`${a.window.height}px`,zIndex:a.window.zIndex});function W(){a.isActive||_.store.focusWindow(a.window.id)}function de(e){a.isBlocked?_.store.dismissDialogFor(a.window.id):e.target.closest(`.pwm-window-controls`)||W()}function fe(){_.store.minimizeWindow(a.window.id)}function pe(){_.store.toggleMaximize(a.window.id)}function me(){_.requestClose(a.window.id)}let G=null,K=0,he=``;function ge(){return Z.value||B.value||V.value||z.value||!!a.window.isClosing}function _e(){let e=x.value;if(!e)return;let t=G&&!ge()?G.transform:null;e.style.transform=t??``,e.style.transformOrigin=t?he:``}function ve(e){if(K=0,!G)return;let t=G.step(e);_e(),t&&(K=requestAnimationFrame(ve))}function q(){!K&&G&&typeof requestAnimationFrame==`function`&&(K=requestAnimationFrame(ve))}function ye(){K&&cancelAnimationFrame(K),K=0,G=null,_e()}r(()=>_.motion.value,e=>{e!==`playful`&&ye()});let J=E(!1),Y=0,X=null,Z=E(!1),Q=E(null);function xe(e,t){var n;try{(n=e.setPointerCapture)==null||n.call(e,t)}catch{}}function Se(e,t){var n;try{(n=e.releasePointerCapture)==null||n.call(e,t)}catch{}}function $(e,t,n,r){let i=!1,a=n=>{if(!(i||n.pointerId!==t)){i=!0;try{r()}finally{window.removeEventListener(`pointermove`,o,!0),window.removeEventListener(`pointerup`,a,!0),window.removeEventListener(`pointercancel`,a,!0),Se(e,t)}}},o=e=>{i||e.pointerId!==t||(e.pointerType===`mouse`&&e.buttons===0?a(e):n(e))};xe(e,t),window.addEventListener(`pointermove`,o,!0),window.addEventListener(`pointerup`,a,!0),window.addEventListener(`pointercancel`,a,!0)}function Ie(e){if(_.isMobile.value||e.button!==0)return;let t=Date.now();if(t-Y<Fe){Y=0;return}Y=t,W();let n=e.currentTarget,r=a.window.x,i=a.window.y,o=e.clientX,s=e.clientY,c=!!a.window.isSnapped||a.window.isMaximized;J.value=!c,_.motion.value===`playful`&&(G??=new be,G.dragStart(o,s)),$(n,e.pointerId,e=>{if(c){if(Math.abs(e.clientX-o)<4&&Math.abs(e.clientY-s)<4)return;c=!1;let t=a.window.isMaximized,n=t?{width:a.window.width,height:a.window.height}:_.store.getPreSnapBounds(a.window.id);if(n){let c=I(a.window,ce(),_.taskbarHeight.value),l=(o-c.x)/c.width;r=o-n.width*l,i=s-20,Q.value=L(c,{x:r+(e.clientX-o),y:i+(e.clientY-s),width:n.width,height:n.height}),t?_.store.restoreWindow(a.window.id):_.store.unSnapWindow(a.window.id)}J.value=!0,Z.value=!0,X=setTimeout(()=>{X=null,Z.value=!1,Q.value=null},200)}C.value=!0,_.store.updateWindowPosition(a.window.id,r+(e.clientX-o),i+(e.clientY-s)),!_.isMobile.value&&P.value.maximizable&&_.store.setSnapPreview(N(e.clientX,e.clientY,ce(),_.taskbarHeight.value)),G&&(he=`${o-r}px ${s-i}px`,G.dragMove(e.clientX,e.clientY),q())},()=>{try{let e=!!_.store.snapPreview&&!_.isMobile.value&&P.value.maximizable;e&&_.store.snapPreview&&_.store.snapWindow(a.window.id,_.store.snapPreview,_.taskbarHeight.value),G&&(G.dragEnd(),e&&G.bounce(),q())}finally{_.store.clearSnapPreview(),X&&=(clearTimeout(X),null),Z.value=!1,Q.value=null,J.value=!1}}),e.preventDefault()}function Le(e){P.value.maximizable&&pe(),e.preventDefault(),e.stopPropagation()}let Re=E(!1);function ze(e,t){if(a.window.isMaximized)return;let n=t.currentTarget,r=t.clientX,i=t.clientY,o=a.window.width,s=a.window.height,c=a.window.x,l=a.window.y;W(),Re.value=!0,$(n,t.pointerId,t=>{let n=P.value,u=ie({direction:e,deltaX:t.clientX-r,deltaY:t.clientY-i,initialX:c,initialY:l,initialWidth:o,initialHeight:s,minWidth:n.minWidth,minHeight:n.minHeight,maxWidth:n.maxWidth,maxHeight:n.maxHeight});_.store.updateWindowSize(a.window.id,u.width,u.height),(u.x!==c||u.y!==l)&&_.store.updateWindowPosition(a.window.id,u.x,u.y)},()=>{Re.value=!1,_.motion.value===`playful`&&(a.window.width!==o||a.window.height!==s)&&(G??=new be,he=`50% 50%`,G.bounce(.5),q())}),t.preventDefault(),t.stopPropagation()}return m(()=>{ae&&clearTimeout(ae),X&&clearTimeout(X),U&&clearTimeout(U),K&&cancelAnimationFrame(K),_.ram&&_.ram.onRestore(a.window.id)}),(r,i)=>s((y(),u(`div`,{class:c([`pwm-window`,[v.value.window,e.isActive?v.value.windowActive:v.value.windowInactive,{"pwm-active":e.isActive,"pwm-dialog":e.window.kind===`dialog`,"pwm-maximized":e.window.isMaximized,"pwm-fullscreen-mobile":o(_).isMobile.value&&e.window.kind!==`dialog`,"pwm-dragging":J.value,"pwm-resizing":Re.value,"pwm-closing":e.window.isClosing,"pwm-unsnapping":Z.value,"pwm-minimizing":B.value,"pwm-restoring":V.value,"pwm-minimize-target":(B.value||V.value)&&!!H.value,"pwm-opening":z.value,"pwm-playful":o(_).motion.value===`playful`,[`pwm-${o(_).appearance.value}`]:!0}]]),ref_key:`rootEl`,ref:x,"data-pwm-window":e.window.id,"data-pwm-blocked":e.isBlocked?``:void 0,"data-pwm-autoheight":e.window.autoHeight?``:void 0,style:f([ue.value,le.value]),onMousedown:de},[l(`div`,{class:c([`pwm-window-header`,v.value.titleBar]),inert:e.isBlocked||void 0},[l(`div`,{class:`pwm-window-header-draggable`,onPointerdown:Ie,onDblclick:Le},[l(`div`,{class:c([`pwm-window-icon-container`,e.isActive?v.value.iconContainerActive:v.value.iconContainer])},[A(r.$slots,`icon`,{window:e.window},()=>[i[0]||=l(`svg`,{class:`pwm-fallback-icon`,"data-glyph":`window`,viewBox:`0 0 24 24`,fill:`currentColor`,"aria-hidden":`true`},[l(`path`,{d:`M21.53 5.15a.99.99 0 0 0-.97-.04l-10 5a1 1 0 0 0-.55.89v10a1 1 0 0 0 1 1c.15 0 .31-.04.45-.11l10-5a1 1 0 0 0 .55-.89V6c0-.35-.18-.67-.47-.85ZM20 15.38l-8 4v-7.76l8-4z`}),l(`path`,{d:`m16.55 3.11l-10 5A1 1 0 0 0 6 9v10h2V9.62l9.45-4.72l-.89-1.79Z`}),l(`path`,{d:`m12.55 1.11l-10 5A1 1 0 0 0 2 7v10h2V7.62l9.45-4.73l-.89-1.79Z`})],-1)])],2),l(`span`,{class:c([`pwm-window-title`,e.isActive?v.value.titleActive:v.value.title])},[n(S(e.window.title)+` `,1),A(r.$slots,`titleBarExtra`,{window:e.window})],2)],32),l(`div`,De,[(y(!0),u(b,null,d(ne.value,t=>(y(),u(b,{key:t},[t===`minimize`&&P.value.minimizable?(y(),u(`button`,{key:0,type:`button`,class:c([`pwm-window-control pwm-minimize`,v.value.control]),title:o(_).labels.minimize,"aria-label":`minimize`,onClick:M(fe,[`stop`])},[A(r.$slots,`minimize-icon`,{window:e.window},()=>[i[1]||=l(`svg`,{class:`pwm-fallback-icon`,"data-glyph":`minimize`,viewBox:`0 0 24 24`,fill:`none`,stroke:`currentColor`,"stroke-width":`2`,"stroke-linecap":`round`,"aria-hidden":`true`},[l(`path`,{d:`M5 12h14`})],-1)])],10,Oe)):t===`maximize`&&!o(_).isMobile.value&&P.value.maximizable?(y(),u(`button`,{key:1,type:`button`,class:c([`pwm-window-control pwm-maximize`,v.value.control]),title:e.window.isMaximized?o(_).labels.restore:o(_).labels.maximize,"aria-label":`maximize`,onClick:M(pe,[`stop`])},[A(r.$slots,`maximize-icon`,{window:e.window},()=>[(y(),u(`svg`,{class:`pwm-fallback-icon`,"data-glyph":e.window.isMaximized?`restore`:`maximize`,viewBox:`0 0 24 24`,fill:`none`,stroke:`currentColor`,"stroke-width":`2`,"stroke-linejoin":`round`,"aria-hidden":`true`},[e.window.isMaximized?(y(),u(b,{key:0},[i[2]||=l(`path`,{d:`M8.5 8.5V6.5A1.5 1.5 0 0 1 10 5h7.5A1.5 1.5 0 0 1 19 6.5V14a1.5 1.5 0 0 1-1.5 1.5h-2`},null,-1),i[3]||=l(`rect`,{x:`5`,y:`8.5`,width:`10.5`,height:`10.5`,rx:`1.5`},null,-1),i[4]||=l(`path`,{d:`M5 12h10.5`},null,-1)],64)):(y(),u(b,{key:1},[i[5]||=l(`rect`,{x:`5`,y:`5`,width:`14`,height:`14`,rx:`1.5`},null,-1),i[6]||=l(`path`,{d:`M5 9h14`},null,-1)],64))],8,Ae))])],10,ke)):t===`close`&&P.value.closeable?(y(),u(`button`,{key:2,type:`button`,class:c([`pwm-window-control pwm-close`,v.value.closeControl]),title:o(_).labels.close,"aria-label":`close`,onClick:M(me,[`stop`])},[A(r.$slots,`close-icon`,{window:e.window},()=>[i[7]||=l(`svg`,{class:`pwm-fallback-icon`,"data-glyph":`close`,viewBox:`0 0 24 24`,fill:`none`,stroke:`currentColor`,"stroke-width":`2`,"stroke-linecap":`round`,"aria-hidden":`true`},[l(`path`,{d:`M6 6l12 12M18 6L6 18`})],-1)])],10,je)):j(``,!0)],64))),128))])],10,Ee),l(`div`,{class:c([`pwm-window-body`,v.value.body]),inert:e.isBlocked||void 0},[e.window.external?(y(),u(`div`,{key:0,class:`pwm-window-slot`,"data-pwm-slot":e.window.id},null,8,Ne)):R.value&&se.value?(y(),T(k(R.value),t(p({key:1},e.window.data)),null,16)):A(r.$slots,`loading`,{key:2},()=>[i[8]||=l(`div`,{class:`pwm-window-loading`},[l(`svg`,{class:`pwm-loading-icon`,viewBox:`0 0 24 24`,fill:`none`,role:`status`,"aria-label":`Loading`},[l(`path`,{stroke:`currentColor`,"stroke-linecap":`round`,"stroke-linejoin":`round`,"stroke-width":`2`,d:`M12 3c4.97 0 9 4.03 9 9`})])],-1)])],10,Me),!e.window.isMaximized&&!o(_).isMobile.value&&P.value.resizable?(y(),u(b,{key:0},d(O,e=>l(`div`,{key:e,class:c([`pwm-resize-handle`,`pwm-resize-${e}`]),onPointerdown:M(t=>ze(e,t),[`stop`])},null,42,Pe)),64)):j(``,!0)],46,Te)),[[re,!e.window.isMinimized||B.value]])}}),Ie={key:0,class:`pwm-modal-layer`},Le=v({__name:`PrismWindowManager`,props:{store:{},resolveComponent:{},resolveConfig:{type:Function,default:void 0},taskbarHeight:{default:0},isMobile:{type:Boolean,default:!1},labels:{default:void 0},classes:{default:void 0},enableRamManager:{type:Boolean,default:!0},appearance:{default:`redmond`},motion:{default:void 0}},setup(e){let t=e,n=Q(t.store),i=h(()=>n.value.windows),a=h(()=>n.value.activeWindowId),s=h(()=>n.value.snapPreview),te=h(()=>n.value.windows.filter(e=>e.kind===`dialog`&&!e.isClosing)),_=h(()=>n.value.windows.filter(e=>e.kind===`dialog`&&(e.modality??`app`)===`app`)),v=h(()=>_.value.filter(e=>!e.isClosing)),S=h(()=>{let e=v.value.length?v.value:_.value;return e.length?Math.min(...e.map(e=>e.zIndex))-1:null}),C=h(()=>_.value.length>0&&v.value.length===0),E=e=>e.kind===`dialog`&&(e.modality??`app`)===`app`,k=h(()=>i.value.filter(E)),ne=h(()=>i.value.filter(e=>!E(e))),re=h(()=>new Set(te.value.filter(e=>e.modality===`window`&&e.ownerId).map(e=>e.ownerId))),M=h(()=>({...Se,...t.classes})),N=t.enableRamManager?new W:null,P=new Map;async function F(e){await t.store.requestClose(e)}r(()=>n.value.windows,e=>{for(let n of e)n.isClosing&&!P.has(n.id)&&P.set(n.id,setTimeout(()=>{P.delete(n.id),t.store.closeWindow(n.id)},200))},{immediate:!0});let ie={store:t.store,ram:N,resolveComponent:t.resolveComponent,resolveConfig:t.resolveConfig??(()=>void 0),isMobile:O(t,`isMobile`),appearance:O(t,`appearance`),motion:h(()=>t.motion??n.value.motion),taskbarHeight:O(t,`taskbarHeight`),labels:{...xe,...t.labels},classes:M,requestClose:F};g(Ce,ie);function I(e){if(e.key===`Escape`){let n=t.store.dialogs;if(n.length){F(n.reduce((e,t)=>t.zIndex>e.zIndex?t:e).id),e.preventDefault();return}}let n=a.value;n&&(e.key===`Escape`||e.altKey&&e.key===`F4`)&&(F(n),e.preventDefault())}let L=null;function R(){L=setTimeout(()=>{L=null;let e=document.activeElement;if(!e||e.tagName!==`IFRAME`)return;let n=e.closest(`[data-pwm-window]`)?.getAttribute(`data-pwm-window`);n&&n!==t.store.activeWindowId&&t.store.getWindowById(n)&&t.store.focusWindow(n)})}return ee(()=>{document.addEventListener(`keydown`,I),window.addEventListener(`blur`,R)}),m(()=>{document.removeEventListener(`keydown`,I),window.removeEventListener(`blur`,R),L&&clearTimeout(L),P.forEach(clearTimeout),P.clear(),N?.dispose()}),(t,n)=>(y(),u(b,null,[l(`div`,{class:c([`pwm-manager`,M.value.manager])},[s.value?(y(),u(`div`,{key:0,class:c([`pwm-snap-preview`,[`pwm-snap-${s.value}`,{"pwm-playful":ie.motion.value===`playful`},M.value.snapPreview]]),style:f(o(z)(s.value,e.taskbarHeight))},null,6)):j(``,!0),(y(!0),u(b,null,d(ne.value,e=>(y(),T($,{key:e.id,window:e,"is-active":e.id===a.value,"is-blocked":re.value.has(e.id)},D({icon:x(e=>[A(t.$slots,`icon`,p({ref_for:!0},e))]),titleBarExtra:x(e=>[A(t.$slots,`titleBarExtra`,p({ref_for:!0},e))]),_:2},[t.$slots.loading?{name:`loading`,fn:x(()=>[A(t.$slots,`loading`)]),key:`0`}:void 0,t.$slots[`minimize-icon`]?{name:`minimize-icon`,fn:x(e=>[A(t.$slots,`minimize-icon`,p({ref_for:!0},e))]),key:`1`}:void 0,t.$slots[`maximize-icon`]?{name:`maximize-icon`,fn:x(e=>[A(t.$slots,`maximize-icon`,p({ref_for:!0},e))]),key:`2`}:void 0,t.$slots[`close-icon`]?{name:`close-icon`,fn:x(e=>[A(t.$slots,`close-icon`,p({ref_for:!0},e))]),key:`3`}:void 0]),1032,[`window`,`is-active`,`is-blocked`]))),128))],2),(y(),T(w,{to:`body`},[S.value!==null||k.value.length?(y(),u(`div`,Ie,[S.value===null?j(``,!0):(y(),u(`div`,{key:0,class:c([`pwm-scrim`,{"pwm-scrim-closing":C.value}]),style:f({zIndex:S.value}),onMousedown:n[0]||=t=>e.store.dismissTopDialog()},null,38)),(y(!0),u(b,null,d(k.value,e=>(y(),T($,{key:e.id,window:e,"is-active":e.id===a.value,"is-blocked":re.value.has(e.id)},D({icon:x(e=>[A(t.$slots,`icon`,p({ref_for:!0},e))]),titleBarExtra:x(e=>[A(t.$slots,`titleBarExtra`,p({ref_for:!0},e))]),_:2},[t.$slots.loading?{name:`loading`,fn:x(()=>[A(t.$slots,`loading`)]),key:`0`}:void 0,t.$slots[`minimize-icon`]?{name:`minimize-icon`,fn:x(e=>[A(t.$slots,`minimize-icon`,p({ref_for:!0},e))]),key:`1`}:void 0,t.$slots[`maximize-icon`]?{name:`maximize-icon`,fn:x(e=>[A(t.$slots,`maximize-icon`,p({ref_for:!0},e))]),key:`2`}:void 0,t.$slots[`close-icon`]?{name:`close-icon`,fn:x(e=>[A(t.$slots,`close-icon`,p({ref_for:!0},e))]),key:`3`}:void 0]),1032,[`window`,`is-active`,`is-blocked`]))),128))])):j(``,!0)]))],64))}}),Re=[`disabled`],ze={key:0,class:`pwm-dialog-spinner`,"aria-hidden":`true`},Be={key:1},Ve=v({__name:`PrismDialog`,props:{store:{},classes:{},visible:{type:Boolean,default:!1},title:{default:``},icon:{},width:{default:420},modality:{default:`app`},ownerId:{},maskClosable:{type:Boolean,default:!1},okText:{default:`OK`},cancelText:{default:`Cancel`},dismissText:{default:``},okCancel:{type:Boolean,default:!0},okDisabled:{type:Boolean,default:!1},okDanger:{type:Boolean,default:!1},loading:{type:Boolean,default:!1},reverseButtons:{type:Boolean,default:!1},closeOnOk:{type:Boolean,default:!0},footer:{type:Boolean,default:!0}},emits:[`update:visible`,`ok`,`cancel`,`dismiss`],setup(e,{expose:t,emit:n}){let o=e,s=n,d=i(Ce,null),ee=a(),f=h(()=>o.store??d?.store??null),p=h(()=>({...Se,...d?.classes.value??{},...o.classes??{}})),te=h(()=>o.footer&&!ee.footer),m=E(null),g=E(null);function v(){if(!f.value||g.value)return;let e=f.value.openDialog(Y,{external:!0,title:o.title,icon:o.icon??null,width:o.width,modality:o.modality,ownerId:o.ownerId,maskClosable:o.maskClosable,onResult:()=>{g.value&&(g.value=null,m.value=null,s(`cancel`),s(`update:visible`,!1))}});g.value=e,b(e)}async function b(e){await C(),await C(),g.value===e&&(m.value=document.querySelector(`[data-pwm-slot="${e}"]`))}function x(){let e=g.value;e&&f.value&&(g.value=null,m.value=null,f.value.beginClose(e))}function D(){s(`ok`),o.closeOnOk&&(x(),s(`update:visible`,!1))}function O(){x(),s(`cancel`),s(`update:visible`,!1)}function k(){x(),s(`dismiss`),s(`update:visible`,!1)}return r(()=>o.visible,e=>e?v():x(),{immediate:!0}),r(()=>o.title,e=>{g.value&&f.value&&f.value.updateWindowTitle(g.value,e)}),_(x),t({close:x}),(t,n)=>m.value?(y(),T(w,{key:0,to:m.value},[A(t.$slots,`default`),A(t.$slots,`footer`,{ok:D,cancel:O,dismiss:k},()=>[te.value?(y(),u(`div`,{key:0,class:c([`pwm-dialog-footer`,[p.value.dialogFooter,{"pwm-dialog-footer-reversed":e.reverseButtons}]])},[e.okCancel?(y(),u(`button`,{key:0,type:`button`,class:c([`pwm-dialog-btn`,p.value.dialogButton]),onClick:O},S(e.cancelText),3)):j(``,!0),e.dismissText?(y(),u(`button`,{key:1,type:`button`,class:c([`pwm-dialog-btn`,p.value.dialogButton]),onClick:k},S(e.dismissText),3)):j(``,!0),l(`button`,{type:`button`,class:c([`pwm-dialog-btn`,[e.okDanger?p.value.dialogButtonDanger:p.value.dialogButtonPrimary,{"pwm-dialog-btn-loading":e.loading}]]),disabled:e.loading||e.okDisabled,onClick:D},[e.loading?(y(),u(`span`,ze)):(y(),u(`span`,Be,S(e.okText),1))],10,Re)],2)):j(``,!0)])],8,[`to`])):j(``,!0)}});export{K as a,be as c,Y as i,G as l,Le as n,fe as o,X as r,de as s,Ve as t,W as u};