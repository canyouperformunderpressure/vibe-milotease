var O=Object.defineProperty;var C=(t,e,n)=>e in t?O(t,e,{enumerable:!0,configurable:!0,writable:!0,value:n}):t[e]=n;var v=(t,e,n)=>(C(t,typeof e!="symbol"?e+"":e,n),n);import{b as g,n as y,j as h,C as L}from"./index-3db13f53.js";function _(t){var e=t.getBoundingClientRect();return{width:e.width,height:e.height,top:"x"in e?e.x:e.top,left:"y"in e?e.y:e.left,x:"x"in e?e.x:e.left,y:"y"in e?e.y:e.top,right:e.right,bottom:e.bottom}}function N(){var t=arguments.length>0&&arguments[0]!==void 0?arguments[0]:{},e=t.liveMeasure,n=e===void 0?!0:e,a=g.useState({}),d=a[0],u=a[1],r=g.useState(null),s=r[0],c=r[1],i=g.useCallback(function(o){c(o)},[]);return g.useLayoutEffect(function(){if(s){var o=function(){return window.requestAnimationFrame(function(){return u(_(s))})};if(o(),n)return window.addEventListener("resize",o),window.addEventListener("scroll",o),function(){window.removeEventListener("resize",o),window.removeEventListener("scroll",o)}}},[s]),[i,d,s]}const w=10,j=t=>t<=640?2:t<=1280?4:t<=1920?5:6,A=y.div`
  display: flex;
  flex-flow: row wrap;
  margin: -${({spaceBetweenItems:t=w})=>t/2}px;

  & > * {
    margin: ${({spaceBetweenItems:t=w})=>t/2}px;
  }
`,T=({imageData:t,width:e,spaceBetweenItems:n=w,component:a,itemProps:d})=>{if(!e)return h.jsx("div",{});const u=j(e),r=[];let s=[],c=0,i=0;for(const[l,m]of t.entries())if(i+=m.aspectRatio,s.push(m),i>=u||l+1>=t.length){i=Math.max(i,u);const f=(e-n*(s.length-1))/i;let p=0;for(const x of s){const M=f*x.aspectRatio;r.push({...x,width:M,height:f,offsetX:p,offsetY:c,entry:x}),p+=M+n}s=[],i=0,c+=f+n}const o=a||"img";return h.jsx(A,{children:r.map(({hash:l,width:m,height:E,url:f,...p},x)=>h.jsx(o,{hash:l,src:f,width:m,height:E,...p,alt:"",...d},l))})},b=0,S=10,R=y(L)`
  transition: box-shadow 0.5s;

  img {
    display: block;
    cursor: pointer;
    box-sizing: border-box;
  }

  &.selected img {
    border: 6px solid ${({theme:t})=>t.palette.secondary.main};
  }
`;class W extends g.Component{constructor(){super(...arguments);v(this,"state",{shadow:b});v(this,"onMouseOver",()=>{this.setState({shadow:S})});v(this,"onMouseOut",()=>{this.setState({shadow:b})})}render(){const{src:n,width:a,height:d,onClick:u,selected:r,imageProps:s}=this.props,{shadow:c}=this.state;return h.jsx(R,{onMouseOver:this.onMouseOver,onMouseOut:this.onMouseOut,elevation:c,className:r?"selected":"",children:h.jsx("img",{src:n,width:a,height:d,alt:"",crossOrigin:"anonymous",onClick:u,...s})})}}export{W as H,T as I,N as u};
