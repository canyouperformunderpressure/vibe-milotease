import{n as s,j as o,T as p,ap as l,bg as x}from"./index-3db13f53.js";import{C as g}from"./CodeEditor-951c2f63.js";import{S as h}from"./Switch-58477672.js";const b=s.div`
  position: relative;
`,u=s.div`
  position: relative;
`,j=s.div`
  position: relative;
  padding: ${({theme:i})=>i.spacing(1)} 0 ${({theme:i})=>i.spacing(2)};
  border-radius: ${({theme:i})=>i.shape.borderRadius}px;
  background-color: #c5cbe9;
  display: flex;
  flex-direction: column;
`,$=s.div`
  position: relative;
  height: 150px;
`,m=s(p).attrs({variant:"subtitle2"})`
  padding: 0 ${({theme:i})=>i.spacing(2)} ${({theme:i})=>i.spacing(1)};
`,C=s(l)`
  position: absolute;
  top: 0;
  right: 0;
  padding: 0 ${({theme:i})=>i.spacing(1)};
  margin-left: ${({theme:i})=>i.spacing(2)};
  display: flex;
  flex-direction: row;
  align-items: center;
  border-radius: ${({theme:i})=>i.shape.borderRadius}px;
  height: ${({theme:i})=>i.spacing(4)};
  background-color: #c5cbe9;
  z-index: 2;
`,f=({elevation:i,checked:t,onChange:r,...n})=>o.jsxs(C,{elevation:i,...n,children:[o.jsx(x,{}),o.jsx(h,{checked:t,onChange:r,color:"secondary"})]}),S=({value:i,defaultValue:t,onChange:r,children:n,controlsProps:a={},hint:d=null})=>{const e=i&&i.startsWith("$");return o.jsxs(b,{children:[o.jsx(f,{checked:!!e,elevation:e?0:2,onChange:()=>r(e?t:"$"),...a}),e?o.jsxs(u,{children:[o.jsxs(j,{children:[o.jsx(m,{children:"Eval"}),o.jsx($,{children:o.jsx(g,{script:i.slice(1),onChange:c=>r("$"+c),allowExpressions:!0})})]}),d]}):n]})};export{S};
