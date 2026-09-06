import{g as x,n as o,Y as E,Z as d,j as a,b as g,a3 as j,a0 as h,v as n}from"./index-3db13f53.js";const u=x`
  query validateScript($teaseId: ID!, $script: String) {
    validateEosScript(teaseId: $teaseId, script: $script) {
      validationErrors {
        property
        message
      }
    }
  }
`,I=o(E)``,V=o(d).attrs({})``,$=o(d).attrs({})``,c=/^pages\.([a-zA-Z0-9-]+)\[([0-9]+)\]\./,l=/^pages\.([a-zA-Z0-9-]+)/,m=({teaseId:s,validationError:t})=>{let{property:e,message:r}=t;if(e==="pages.start"&&r==="The property start is required")r='Your tease must have a page called "start"';else if(c.exec(e)){const[,i,p]=c.exec(e);e=a.jsx(n,{to:`/${s}/edit/${i}/action/${p}`,children:e})}else if(l.exec(e)){const[,i]=l.exec(e);e=a.jsx(n,{to:`/${s}/edit/${i}`,children:e})}return a.jsxs(I,{children:[a.jsx(V,{children:e}),a.jsx($,{children:r})]})},v=({teaseId:s,validationErrors:t})=>a.jsx(g.Fragment,{children:a.jsx(j,{children:a.jsx(h,{children:t.map((e,r)=>a.jsx(m,{teaseId:s,validationError:e},r))})})});export{u as V,v as a};
