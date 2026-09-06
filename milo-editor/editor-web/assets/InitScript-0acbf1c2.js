import{m as r,n as o,b as a,j as t,q as c,aR as p,E as d,a as h,T as s}from"./index-3db13f53.js";import{C as l}from"./CodeEditor-951c2f63.js";import{I as m}from"./InfoCard-9ae168c0.js";const x=({script:{init:e}})=>({init:e}),u=o.div`
  display: flex;
  height: 100%;
  flex-direction: column;
  overflow: hidden;
`;class f extends a.Component{render(){const{init:i}=this.props;return t.jsxs(u,{children:[t.jsx(c,{subheader:t.jsx(p,{children:"Init Script"})}),t.jsx(l,{script:i,focus:!0,minLines:20,onChange:n=>d.setInitScript({init:n})}),i?null:t.jsx(m,{children:t.jsxs(h,{children:[t.jsx(s,{gutterBottom:!0,variant:"h6",component:"h2",children:"More Information"}),t.jsxs(s,{component:"p",children:["The ",t.jsx("strong",{children:"Init Script"})," is a piece of JavaScript which is executed every time your tease is loaded. This is a great place to initialize variables, define reusable functions, and so on."]})]})})]})}}const S=r(x)(f);export{S as default};
