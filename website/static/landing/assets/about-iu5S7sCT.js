import{B as e,G as t,H as n,c as r,i,l as a,t as o,z as s}from"./i18n-CezZdh_C.js";import{t as c}from"./Blob-BTDnLUC1.js";var l=t(n(),1),u=t(e(),1),d=s(),f=[.16,1,.3,1];function p(e){return r[e]?.en}function m(){let e=o===`he`;return(0,d.jsxs)(`div`,{id:`todira-about-root`,children:[(0,d.jsx)(c,{style:{width:340,height:340,top:-100,insetInlineStart:`-6%`,background:`var(--gold-light)`,opacity:.3},animate:{x:[0,30,-15,0],y:[0,-20,15,0],scale:[1,1.08,.96,1]},duration:18}),(0,d.jsx)(c,{style:{width:300,height:300,bottom:-80,insetInlineEnd:`-8%`,background:`var(--teal)`,opacity:.2},animate:{x:[0,-25,15,0],y:[0,20,-15,0],scale:[1,.92,1.06,1]},duration:22}),(0,d.jsxs)(`section`,{style:{position:`relative`,zIndex:1,maxWidth:680,textAlign:`center`},children:[o!==`he`&&o!==`en`&&(0,d.jsx)(a.div,{initial:{opacity:0,y:12},animate:{opacity:1,y:0},transition:{duration:.5,ease:f},className:`notice`,style:{marginBottom:22},children:i(`legal.non_native_notice`)}),(0,d.jsx)(a.h1,{initial:{opacity:0,y:24,scale:.97},animate:{opacity:1,y:0,scale:1},transition:{duration:.7,ease:f},className:`tl-about-h1`,children:e?i(`about.h1`):p(`about.h1`)||`About Todira`}),(0,d.jsx)(a.p,{initial:{opacity:0,y:18},animate:{opacity:1,y:0},transition:{duration:.6,delay:.15,ease:f},style:{fontSize:`1.08rem`,color:`var(--text-muted)`,lineHeight:1.75,marginTop:26},children:e?i(`about.body_intro`):p(`about.body_intro`)}),(0,d.jsx)(a.p,{initial:{opacity:0,y:18},animate:{opacity:1,y:0},transition:{duration:.6,delay:.28,ease:f},style:{fontSize:`1.08rem`,color:`var(--text-muted)`,lineHeight:1.75,marginTop:18},children:e?i(`about.body_disclaimer`):p(`about.body_disclaimer`)}),(0,d.jsxs)(a.p,{initial:{opacity:0,y:18},animate:{opacity:1,y:0},transition:{duration:.6,delay:.4,ease:f},style:{fontSize:`1.08rem`,color:`var(--text-muted)`,lineHeight:1.75,marginTop:18},children:[e?i(`about.links_p1`):p(`about.links_p1`),(0,d.jsx)(`a`,{href:`/terms`,children:e?i(`about.link_terms`):p(`about.link_terms`)}),e?i(`about.links_p2`):p(`about.links_p2`),(0,d.jsx)(`a`,{href:`/privacy`,children:e?i(`about.link_privacy`):p(`about.link_privacy`)}),e?i(`about.links_p3`):p(`about.links_p3`),(0,d.jsx)(`a`,{href:`/contact`,children:e?i(`about.link_contact_page`):p(`about.link_contact_page`)}),e?i(`about.links_p4`):p(`about.links_p4`)]})]}),(0,d.jsx)(`style`,{children:`
        #todira-about-root {
          position: relative; overflow: hidden;
          padding: clamp(48px, 8vw, 96px) 24px;
          display: flex; justify-content: center;
        }
        .tl-about-h1 {
          margin: 0; font-size: clamp(2rem, 6vw, 3rem);
          background: linear-gradient(90deg, var(--heading) 0%, var(--teal) 40%, var(--gold) 70%, var(--heading) 100%);
          background-size: 200% auto; -webkit-background-clip: text; background-clip: text; color: transparent;
          animation: tl-about-shine 9s linear infinite;
        }
        @keyframes tl-about-shine { to { background-position: -200% center; } }
        @media (prefers-reduced-motion: reduce) { .tl-about-h1 { animation: none; } }
        #todira-about-root .notice {
          background: var(--teal-tint); color: var(--heading); border-radius: 12px;
          padding: 12px 18px; font-size: .9rem;
        }
        #todira-about-root a { color: var(--teal); font-weight: 600; text-decoration: underline; text-underline-offset: 2px; }
      `})]})}var h=document.getElementById(`root`);h&&(0,u.createRoot)(h).render((0,d.jsx)(l.StrictMode,{children:(0,d.jsx)(m,{})}));