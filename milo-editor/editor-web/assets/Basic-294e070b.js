import{j as e,f as y,h as D,D as f,k as C,l as B,e as b,B as r,m as P,g as E,n as S,ag as V,b as o,ax as m,p as F,q as p,aR as x,s as k,V as I,aU as M,w as j,P as Q,aV as g,E as G}from"./index-3db13f53.js";const N=({open:t,value:a,onClose:n,onConfirm:i,onChange:l})=>e.jsxs(y,{open:t,onClose:n,"aria-labelledby":"form-dialog-title",children:[e.jsx(D,{id:"form-dialog-title",children:"Change Title"}),e.jsxs(f,{children:[e.jsx(C,{children:"Please enter the new title for this tease"}),e.jsx(B,{autoFocus:!0,margin:"dense",id:"title",label:"Title",variant:"filled",fullWidth:!0,value:a,onChange:l})]}),e.jsxs(b,{children:[e.jsx(r,{onClick:n,color:"primary",children:"Cancel"}),e.jsx(r,{onClick:i,color:"primary",children:"Rename"})]})]}),U=({open:t,value:a,onClose:n,onConfirm:i,onChange:l})=>e.jsxs(y,{open:t,onClose:n,"aria-labelledby":"form-dialog-title",children:[e.jsx(D,{id:"form-dialog-title",children:"Delete Tease"}),e.jsx(f,{children:e.jsxs(C,{children:["Are you sure you want to ",e.jsx("strong",{children:"irrevocably"})," delete the entire tease?"]})}),e.jsxs(b,{children:[e.jsx(r,{onClick:n,children:"Cancel"}),e.jsx(r,{onClick:i,color:"primary",children:"Delete"})]})]}),W=({title:t,teaseId:a})=>({title:t,teaseId:a}),z=E`
  mutation SetTeaseTitle($teaseId: ID!, $title: String!) {
    setTeaseTitle(teaseId: $teaseId, title: $title) {
      id
      title
    }
  }
`,H=E`
  mutation DeleteTease($teaseId: ID!) {
    deleteTease(teaseId: $teaseId)
  }
`,J=S(k)`
  background-color: ${({theme:t})=>t.palette.error.dark};
  color: ${({theme:t})=>t.palette.error.contrastText};

  &:hover {
    background-color: ${({theme:t})=>V(t.palette.error.dark,.2)};
  }
`,K=S(I)`
  color: inherit;
`,X=({teaseId:t,title:a})=>{const[n,i]=o.useState(!1),[l,c]=o.useState(!1),[v,d]=o.useState(!1),[R]=m(H,{variables:{teaseId:t},update:s=>{const{me:u}=s.readQuery({query:g});s.writeQuery({query:g,data:{me:{...u,allTeases:u.allTeases.filter(w=>w.id!==t)}}})}}),[$]=m(z,{variables:{teaseId:t,title:l},optimisticResponse:{__typename:"Mutation",setTeaseTitle:{__typename:"EosTease",id:String(t),title:l}},onCompleted:()=>G.updateTitle({title:l})}),L=F(),_=s=>{i(!0),c(s)},h=()=>{i(!1)},O=s=>{c(s.target.value)},A=s=>{d(!0)},T=()=>{d(!1)},q=s=>{T(),s(),L("/teases")};return e.jsxs(e.Fragment,{children:[e.jsxs(p,{component:"nav",subheader:e.jsx(x,{disableSticky:!0,children:"General Settings"}),children:[e.jsx(N,{open:n,value:l,onClose:h,onChange:O,onConfirm:()=>{h(),$()}}),e.jsxs(k,{button:!0,onClick:()=>_(a),children:[e.jsx(I,{children:e.jsx(M,{})}),e.jsx(j,{primary:"Title",secondary:a})]})]}),e.jsxs(p,{component:"nav",subheader:e.jsx(x,{disableSticky:!0,children:"Other Actions"}),children:[e.jsx(U,{open:v,onClose:T,onConfirm:()=>q(R)}),e.jsxs(J,{button:!0,onClick:A,children:[e.jsx(K,{children:e.jsx(Q,{color:"inherit"})}),e.jsx(j,{primary:"Delete Tease",secondary:"Delete the entire tease",primaryTypographyProps:{color:"inherit"},secondaryTypographyProps:{color:"inherit"}})]})]})]})},Z=P(W)(X);export{Z as default};
