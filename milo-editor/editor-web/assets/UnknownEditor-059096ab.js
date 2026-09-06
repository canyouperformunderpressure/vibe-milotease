import{n as t,b as l,j as n,b7 as a,a as d,T as e}from"./index-3db13f53.js";import{C as p}from"./CodeEditor-951c2f63.js";import{E as c,H as x}from"./HelpDialog-24c7ff5f.js";const u=t.div`
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
`,f=t.div`
  flex: 1;
  display: flex;
  flex-direction: column;
`,C=({type:s,props:r,onChange:h})=>{const[i,o]=l.useState(!1);return n.jsxs(u,{children:[n.jsx(c,{icon:n.jsx(a,{}),title:`Unknown: ${s}`,onHelp:()=>o(!0)}),n.jsx(f,{children:n.jsx(p,{readOnly:!0,script:JSON.stringify(r,null,2),allowExpressions:!0})}),n.jsx(x,{open:i,onClose:()=>o(!1),children:n.jsxs(d,{children:[n.jsx(e,{gutterBottom:!0,variant:"h5",component:"h2",children:"More Information"}),n.jsxs(e,{component:"p",children:["This is an ",n.jsx("strong",{children:"unknown"})," action meaning it's not supported by this editor."]})]})})]})};export{C as default};
