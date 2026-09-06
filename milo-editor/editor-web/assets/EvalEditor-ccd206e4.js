import{n as r,b as l,j as e,bg as p,a as c,T as o}from"./index-3db13f53.js";import{C as d}from"./CodeEditor-951c2f63.js";import{E as f,H as h}from"./HelpDialog-24c7ff5f.js";const x=r.div`
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
`,m=r.div`
  flex: 1;
  display: flex;
  flex-direction: column;
`,v=({props:{script:s},onChange:n})=>{const[i,t]=l.useState(!1);return e.jsxs(x,{children:[e.jsx(f,{icon:e.jsx(p,{}),title:"Eval",onHelp:()=>t(!0)}),e.jsx(m,{children:e.jsx(d,{script:s,onChange:a=>n({script:a}),focus:!0})}),e.jsx(h,{open:i,onClose:()=>t(!1),children:e.jsxs(c,{children:[e.jsx(o,{gutterBottom:!0,variant:"h5",component:"h2",children:"More Information"}),e.jsxs(o,{component:"p",children:["The ",e.jsx("strong",{children:"Eval"})," action executes a piece of JavaScript inside of the tease's virtual script interpreter. Please note that this feature is intended for small snippets of simple code. The interpreter does not have the performance or feature set to run a larger, more complex piece of code."]})]})})]})};export{v as default};
