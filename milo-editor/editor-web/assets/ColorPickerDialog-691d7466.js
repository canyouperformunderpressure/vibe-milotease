import{n as t,bf as l,I as g,bq as A,br as h,bs as x,bt as m,bu as u,bv as $,j as c,f as n,h as j,D as y,e as C,B as k}from"./index-3db13f53.js";import{i as D,y as w}from"./yellow-c3d64e73.js";import{a as S}from"./amber-8c90edc2.js";const v={50:"#fce4ec",100:"#f8bbd0",200:"#f48fb1",300:"#f06292",400:"#ec407a",500:"#e91e63",600:"#d81b60",700:"#c2185b",800:"#ad1457",900:"#880e4f",A100:"#ff80ab",A200:"#ff4081",A400:"#f50057",A700:"#c51162"},P=v,B={50:"#ede7f6",100:"#d1c4e9",200:"#b39ddb",300:"#9575cd",400:"#7e57c2",500:"#673ab7",600:"#5e35b1",700:"#512da8",800:"#4527a0",900:"#311b92",A100:"#b388ff",A200:"#7c4dff",A400:"#651fff",A700:"#6200ea"},O=B,R={50:"#e0f7fa",100:"#b2ebf2",200:"#80deea",300:"#4dd0e1",400:"#26c6da",500:"#00bcd4",600:"#00acc1",700:"#0097a7",800:"#00838f",900:"#006064",A100:"#84ffff",A200:"#18ffff",A400:"#00e5ff",A700:"#00b8d4"},G=R,q={50:"#e0f2f1",100:"#b2dfdb",200:"#80cbc4",300:"#4db6ac",400:"#26a69a",500:"#009688",600:"#00897b",700:"#00796b",800:"#00695c",900:"#004d40",A100:"#a7ffeb",A200:"#64ffda",A400:"#1de9b6",A700:"#00bfa5"},E=q,I={50:"#f1f8e9",100:"#dcedc8",200:"#c5e1a5",300:"#aed581",400:"#9ccc65",500:"#8bc34a",600:"#7cb342",700:"#689f38",800:"#558b2f",900:"#33691e",A100:"#ccff90",A200:"#b2ff59",A400:"#76ff03",A700:"#64dd17"},M=I,T={50:"#f9fbe7",100:"#f0f4c3",200:"#e6ee9c",300:"#dce775",400:"#d4e157",500:"#cddc39",600:"#c0ca33",700:"#afb42b",800:"#9e9d24",900:"#827717",A100:"#f4ff81",A200:"#eeff41",A400:"#c6ff00",A700:"#aeea00"},W=T,z={50:"#fbe9e7",100:"#ffccbc",200:"#ffab91",300:"#ff8a65",400:"#ff7043",500:"#ff5722",600:"#f4511e",700:"#e64a19",800:"#d84315",900:"#bf360c",A100:"#ff9e80",A200:"#ff6e40",A400:"#ff3d00",A700:"#dd2c00"},F=z,H={50:"#efebe9",100:"#d7ccc8",200:"#bcaaa4",300:"#a1887f",400:"#8d6e63",500:"#795548",600:"#6d4c41",700:"#5d4037",800:"#4e342e",900:"#3e2723",A100:"#d7ccc8",A200:"#bcaaa4",A400:"#8d6e63",A700:"#5d4037"},J=H,K=t.div`
  display: flex;
  flex-direction: column;
  margin: ${({theme:e})=>-e.spacing(.5)};

  > div:first-child > div:first-child {
    height: ${({theme:e})=>e.spacing(6)};
  }
`,L=t.div`
  display: flex;
  flex-direction: row;
  align-items: flex-end;
`,N=t.div`
  width: ${({theme:e})=>e.spacing(4)};
  height: ${({theme:e})=>e.spacing(4)};
  cursor: pointer;
  flex: 1;
  margin: ${({theme:e})=>e.spacing(.5)};
  border-radius: ${({theme:e})=>.5*e.shape.borderRadius}px;

  &:hover {
    opacity: 0.8;
  }
`,i=(e,f,a)=>e.map((s,r)=>Object.keys(s).filter(o=>!o.startsWith("A")).map(o=>s[o]).filter(o=>$(o,f)>a)),d=[{0:"#ffffff",...l,1e3:"#000000"},g,P,A,O,D,h,x,G,E,m,M,W,w,S,u,F,J],Q={light:i(d,"#000",5),dark:i(d,"#fff",1.3)},U=({colors:e,onSelect:f})=>c.jsx(L,{children:e.map(a=>c.jsx(N,{style:{backgroundColor:a},onClick:()=>f(a)},a))}),V=({variant:e="light",onSelect:f})=>c.jsx(K,{children:Q[e].map((a,s)=>c.jsx(U,{colors:a,onSelect:f},s))}),X=()=>e=>f=>c.jsx(e,{...f,width:"lg",fullScreen:!1}),Y=t(n)`
  .paper {
    color: #fff;
    background-color: ${l[900]};
  }

  .title > * {
    color: inherit;
  }
`,Z=({title:e="Choose Color",variant:f="light",open:a,color:s,fullScreen:r,onClose:o,onSelect:b})=>{const p=f==="light"?Y:n;return c.jsxs(p,{classes:{paper:"paper"},open:a,fullScreen:r,onClose:o,children:[c.jsx(j,{classes:{root:"title"},children:e}),c.jsx(y,{children:c.jsx(V,{onSelect:b,variant:f})}),c.jsx(C,{children:c.jsx(k,{onClick:o,color:"inherit",children:"Cancel"})})]})},f0=X()(Z);export{f0 as C};
