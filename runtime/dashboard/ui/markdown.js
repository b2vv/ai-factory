import {createElement} from 'react';
import Markdown from 'react-markdown';

const allowedElements=['p','h3','h4','ul','ol','li','strong','em','code','pre','blockquote','a'];
const components={a:({children})=>createElement('span',null,children)};

export function ReviewedMarkdown({children}) {
  return createElement(Markdown,{skipHtml:true,allowedElements,components,urlTransform:()=>''},children);
}
