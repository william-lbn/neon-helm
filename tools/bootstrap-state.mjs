#!/usr/bin/env node
// External mutable state is intentionally outside Helm ownership. Never reset it
// on upgrade: the route catalog includes live endpoint credentials and identities.
import {get,kube} from './lib.mjs';
for(const name of ['neon']) {
  if(!get('namespace',name)) kube(['create','namespace',name]);
}
const objects=[
  {apiVersion:'v1',kind:'Secret',metadata:{name:'neon-control-routes',namespace:'neon'},type:'Opaque',stringData:{'routes.json':'{}'}},
  {apiVersion:'v1',kind:'ConfigMap',metadata:{name:'neon-control-notifications',namespace:'neon'},data:{'receipts.json':'{}'}},
];
for(const obj of objects) {
  if(get(obj.kind,obj.metadata.name,'neon')) {console.log(obj.metadata.name+': preserved');continue;}
  // create is atomic; an already-existing object from another operator fails.
  kube(['create','-f','-'],{input:JSON.stringify(obj)});
  console.log(obj.metadata.name+': initialized');
}
