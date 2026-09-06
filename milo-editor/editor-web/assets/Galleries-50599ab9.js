var J=Object.defineProperty;var K=(r,t,a)=>t in r?J(r,t,{enumerable:!0,configurable:!0,writable:!0,value:a}):r[t]=a;var m=(r,t,a)=>(K(r,typeof t!="symbol"?t+"":t,a),a);import{n as o,j as e,C,T as u,r as Z,i as ee,g as w,a as f,u as P,D as $,F as b,B as h,b as j,c as re,t as ae,L as te,d as se,e as O,f as _,h as le,k as ne,l as ie,m as oe,o as ce,p as de,q as he,s as ge,v as me,w as ue,A as pe,x as D,y as xe,z as H,E as z,G as ye,H as ve}from"./index-3db13f53.js";import{d as je}from"./CloudDownload-201fa32e.js";import{d as N}from"./ChevronLeft-f1237947.js";import{C as B,L as Ce}from"./index.modern-10e327fd.js";import{C as fe}from"./CardMedia-0cbd900b.js";import{u as R,I as be,H as Ge}from"./HoverImageCard-68a6cb19.js";const Ie="/eos/editor/assets/shibari4-3955ec82.svg",we=o.div`
  flex: 1;
  background-image: url(${Ie});
  background-position: center center;
  background-size: contain;
  background-repeat: no-repeat;
  padding: ${({theme:r})=>r.spacing(3)};
`,Pe=o(u).attrs({variant:"body1"})`
  text-align: center;
  padding: ${({theme:r})=>r.spacing(2)};
`,$e=()=>e.jsx(we,{children:e.jsx(C,{children:e.jsx(Pe,{children:"You haven't created any galleries for this tease yet. Galleries are a great way to organize series of images. You can create your own galleries and upload your own images or use some of the pre-made galleries we provide. Click one of the buttons in the bottom right to get started."})})});var S={},Se=ee;Object.defineProperty(S,"__esModule",{value:!0});var q=S.default=void 0,ke=Se(Z()),Le=e;q=S.default=(0,ke.default)((0,Le.jsx)("path",{d:"M19 19H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3z"}),"OpenInNew");const De=r=>(r[0]==="#"&&(r=r.substring(1)),{r:parseInt(r.substring(0,2),16),g:parseInt(r.substring(2,4),16),b:parseInt(r.substring(4,6),16)}),He=r=>{typeof r=="string"&&(r=De(r));const{r:t,g:a,b:s}=r;return t*299+a*587+s*114<123e3?"white":"black"},ze=o(C)`
  margin-bottom: ${({theme:r})=>r.spacing(3)};
`,Ne=o(f)`
  position: relative;
  background-color: #${({color:r})=>r};

  .label {
    color: ${({labelcolor:r})=>r};
  }
`,Te=o.img`
  position: absolute;
  top: 0;
  bottom: 0;
  right: ${({theme:r})=>r.spacing(1)};
  margin: auto 0;
  max-width: 30%;
  max-height: 80%;
`,Oe=o(q)`
  margin-right: ${({theme:r})=>r.spacing(1)};
`,_e=({url:r})=>e.jsxs(h,{size:"small",color:"secondary",onClick:()=>window.open(r,"_blank"),children:[e.jsx(Oe,{classes:{root:"icon"}}),"Visit Website"]}),Be=w`
  query GalleryProviders {
    galleryProviders {
      shortname
      name
      url
      description
      thumbnail
      color
    }
  }
`,Re=({onSelect:r})=>{var a;const{data:t}=P(Be);return e.jsx($,{children:(a=t==null?void 0:t.galleryProviders)==null?void 0:a.map(({shortname:s,name:l,url:n,description:i,thumbnail:c,color:g})=>e.jsxs(ze,{children:[e.jsxs(Ne,{color:g,labelcolor:He(g),children:[e.jsx(Te,{src:c,alt:"Logo"}),e.jsx(u,{variant:"h5",component:"h2",classes:{root:"label"},children:l})]}),e.jsx(f,{children:e.jsx(u,{component:"p",classes:{root:"label"},children:i})}),e.jsxs(B,{children:[e.jsx(_e,{url:n}),e.jsx(b,{}),e.jsx(h,{size:"small",color:"primary",variant:"contained",onClick:()=>r&&r(s),children:"Browse Images"})]})]},s))})},T=700,E=226,qe=o(C)`
  height: ${E}px;
  display: flex;
`,Ee=o.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
`,Me=o(f)`
  flex: 1;
  display: flex;
  flex-direction: column;
`,Ve=o(fe)`
  height: 100%;
`,Ae=o(u)`
  white-space: nowrap;
  text-overflow: ellipsis;
  overflow: hidden;
`,Fe=o(u)``,We=(r,t)=>{const s=r.find(l=>{const{width:n,height:i}=l.mediaHash.dimensions;return t==="portrait"?n<=i:n>=i})||r[0];return s?s.mediaHash.thumbnailLarge:""},Qe=({title:r,description:t,images:a,width:s,onPreview:l,onSelect:n})=>e.jsxs(qe,{children:[e.jsx(Ve,{component:"img",src:We(a,s>T?"landscape":"portrait"),style:{width:s>T?"300px":"150px"},alt:r,crossOrigin:"anonymous"}),e.jsxs(Ee,{children:[e.jsxs(Me,{children:[e.jsx(Ae,{gutterBottom:!0,variant:"h6",component:"h2",children:r}),e.jsx(Fe,{component:"div",children:e.jsx(Ce,{text:t,maxLine:"4",ellipsis:"...",trimRight:!0,basedOn:"letters"})})]}),e.jsxs(B,{children:[e.jsx(b,{}),e.jsx(h,{size:"small",color:"secondary",onClick:l,children:"Preview"}),e.jsx(h,{size:"small",color:"primary",variant:"contained",onClick:n,children:"Import"})]})]})]}),Ye=w`
  query GalleryProvider($provider: String!, $cursor: String) {
    galleryProvider(shortname: $provider) {
      shortname
      name
      url
      thumbnail
      galleriesConnection(first: 30, after: $cursor) {
        edges {
          node {
            id
            title
            description
            images {
              name
              mediaHash {
                id
                hash
                thumbnailLarge
                dimensions {
                  width
                  height
                }
              }
            }
          }
        }
        pageInfo {
          endCursor
          hasNextPage
        }
      }
    }
  }
`,Ue=o.div`
  padding: ${({theme:r})=>`${r.spacing(3)} ${r.spacing(3)} 0`};
  padding-bottom: 0;
`,Xe=({provider:r,onSelect:t,onPreview:a})=>{j.useState(!1);const{loading:s,data:l}=P(Ye,{variables:{provider:r}}),[n,{width:i}]=R(),c=({node:{id:p,title:x,description:y,images:v}},I)=>e.jsx(Ue,{style:I,children:e.jsx(Qe,{title:x,description:y,images:v,width:i,onSelect:()=>t(Number(p)),onPreview:()=>a(p)})},p),G=re({count:(l==null?void 0:l.galleryProvider.galleriesConnection.edges.length)??0,getScrollElement:()=>n.current,estimateSize:()=>E+ae.spacing(3),overscan:5}).getVirtualItems();return s?e.jsx(te,{label:"Loading galleries..."}):e.jsx(b,{ref:n,children:G.map(({key:p,size:x,start:y,index:v})=>c(l.galleryProvider.galleriesConnection.edges[v],{position:"absolute",top:0,left:0,width:"100%",height:`${x}px`,transform:`translateY(${y}px)`}))})},M=w`
  query Gallery($galleryId: Int!) {
    gallery(id: $galleryId) {
      id
      title
      description
      images {
        id
        name
        mediaHash {
          id
          hash
          size
          thumbnailLarge
          dimensions {
            width
            height
          }
        }
      }
    }
  }
`,Je=o(C)`
  margin-bottom: ${({theme:r})=>r.spacing(3)};
`,Ke=({galleryId:r})=>{const{loading:t,data:a}=P(M,{variables:{galleryId:parseInt(r,10)}}),[s,{width:l}]=R();return e.jsx($,{style:{height:"100%",overflowX:"hidden",overflowY:"scroll"},ref:s,children:t?e.jsx(se,{}):e.jsxs(e.Fragment,{children:[e.jsx(Je,{children:e.jsxs(f,{children:[e.jsx(u,{variant:"h6",gutterBottom:!0,children:a.gallery.title}),e.jsx(u,{variant:"body1",gutterBottom:!0,children:a.gallery.description})]})}),e.jsx(be,{width:l,imageData:a.gallery.images.map(({name:n,mediaHash:{hash:i,thumbnailLarge:c,dimensions:g}})=>({name:n,hash:i,url:c,aspectRatio:g.width/g.height})),component:n=>e.jsx(Ge,{...n})})]})})},Ze=()=>r=>t=>e.jsx(r,{...t,width:"lg",fullScreen:!1}),er=o(_)`
  .dialogContainer {
    width: 100%;
    height: 100%;
  }
`;class rr extends j.Component{constructor(){super(...arguments);m(this,"state",{currentProvider:null,currentGallery:null});m(this,"handleSelectProvider",a=>{this.setState({currentProvider:a})});m(this,"handleCancelProvider",()=>{this.setState({currentProvider:null,currentGallery:null})});m(this,"handlePreviewGallery",a=>{this.setState({currentGallery:a})});m(this,"handleCancelGallery",()=>{this.setState({currentGallery:null})});m(this,"handleSelectGallery",a=>{if(this.props.onChoose){const{currentProvider:s}=this.state;this.props.onChoose(s,a)}})}render(){const{fullScreen:a,open:s,onClose:l,single:n}=this.props,{currentProvider:i,currentGallery:c}=this.state;return e.jsxs(er,{fullScreen:a,open:s,onClose:l,maxWidth:"md","aria-labelledby":"responsive-dialog-title",classes:{paper:"dialogContainer"},children:[c!==null?e.jsx(Ke,{single:n,galleryId:c,onSelect:()=>this.handleSelectGallery(c)}):i?e.jsx(Xe,{single:n,provider:i,onPreview:this.handlePreviewGallery,onSelect:this.handleSelectGallery}):e.jsx(Re,{onSelect:this.handleSelectProvider}),e.jsxs(O,{children:[i?c?e.jsxs(h,{onClick:this.handleCancelGallery,children:[e.jsx(N,{}),"Back to Gallery List"]}):e.jsxs(h,{onClick:this.handleCancelProvider,children:[e.jsx(N,{}),"Back to Provider List"]}):null,e.jsx(b,{}),e.jsx(h,{onClick:l,children:"Close"}),i&&c?e.jsx(h,{color:"primary",variant:"contained",onClick:()=>this.handleSelectGallery(Number(c)),children:"Import"}):null]})]})}}const ar=Ze()(rr),tr=({open:r,value:t,onClose:a,onConfirm:s,onChange:l})=>e.jsxs(_,{open:r,onClose:a,"aria-labelledby":"form-dialog-title",children:[e.jsx(le,{id:"form-dialog-title",children:"Create New Gallery"}),e.jsxs($,{children:[e.jsx(ne,{children:"Please enter the name of the new gallery."}),e.jsx(ie,{autoFocus:!0,margin:"dense",id:"name",label:"Name",variant:"filled",fullWidth:!0,value:t,onChange:l})]}),e.jsxs(O,{children:[e.jsx(h,{onClick:a,color:"primary",children:"Cancel"}),e.jsx(h,{onClick:s,color:"primary",children:"Create"})]})]}),sr=o(ve)`
  flex: 1;
  display: flex;
  flex-direction: column;
`,lr=o.div`
  position: absolute;
  bottom: ${({theme:r})=>r.spacing(2)};
  right: ${({theme:r})=>r.spacing(2)};
  display: flex;
  flex-direction: column;

  > button {
    margin-top: ${({theme:r})=>r.spacing(2)};
  }
`,nr=({teaseId:r,script:t})=>({teaseId:r,script:t}),ir=({script:r})=>{const[t,a]=j.useState(!1),[s,l]=j.useState(""),[n,i]=j.useState(!1),{teaseId:c}=ce(),g=de(),G=()=>{a(!0),l("")},p=d=>{l(d.target.value)},x=()=>{a(!1)},y=()=>{const d=H();a(!1),z.createGallery({id:d,name:s}),g(`/${c}/galleries/${d}`)},v=()=>{i(!0)},I=()=>{i(!1)},V=async(d,A)=>{const F=H();i(!1);const L=await ye.query({query:M,variables:{galleryId:A}});z.createGallery({id:F,name:L.data.gallery.title,images:L.data.gallery.images.map(({id:W,mediaHash:{hash:Q,size:Y,dimensions:{width:U,height:X}}})=>({id:Number(W),hash:Q,size:Y,width:U,height:X}))})},k=Object.keys(r.galleries).map(d=>({...r.galleries[d],id:d}));return e.jsxs(sr,{children:[e.jsx(tr,{open:t,value:s,onClose:x,onChange:p,onConfirm:y}),e.jsx(ar,{open:n,onClose:I,onChoose:V}),e.jsx(he,{children:k.map(d=>e.jsx(ge,{button:!0,component:me,to:`/${c}/galleries/${d.id}`,children:e.jsx(ue,{children:d.name})},d.name))}),k.length===0?e.jsx($e,{}):null,e.jsx(pe,{position:"fixed",children:e.jsxs(lr,{children:[e.jsx(D,{color:"default",onClick:v,children:e.jsx(je,{})}),e.jsx(D,{color:"primary",onClick:G,children:e.jsx(xe,{})})]})})]})},pr=oe(nr)(ir);export{pr as default};
