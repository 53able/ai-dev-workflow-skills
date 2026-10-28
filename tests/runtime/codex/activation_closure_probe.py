#!/usr/bin/env python3
"""Nonsecret current structural probe; never a historical run receipt.
No model/thread start, credentials read, preference mutation or raw config output.
"""
import ctypes,datetime,hashlib,json,pathlib,sys
from runtime import RPC,OUT,clean
DEST=OUT/'r2/closure-plan'
def mdm_forced():
 cf=ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
 cf.CFStringCreateWithCString.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_uint32];cf.CFStringCreateWithCString.restype=ctypes.c_void_p
 cf.CFPreferencesAppValueIsForced.argtypes=[ctypes.c_void_p,ctypes.c_void_p];cf.CFPreferencesAppValueIsForced.restype=ctypes.c_ubyte
 cf.CFRelease.argtypes=[ctypes.c_void_p]
 def string(x):return cf.CFStringCreateWithCString(None,x.encode(),0x08000100)
 app=string('com.openai.codex');result={}
 try:
  for name in ['config_toml_base64','requirements_toml_base64']:
   key=string(name)
   try:result[name]=bool(cf.CFPreferencesAppValueIsForced(key,app))
   finally:cf.CFRelease(key)
 finally:cf.CFRelease(app)
 return result

def structural(config):
 if not isinstance(config,dict):return {'type':type(config).__name__}
 mcp=config.get('mcp_servers',{});features=config.get('features',{});token=config.get('token_budget',{})
 return {'top_level_keys':sorted(config),'mcp_server_names':sorted(mcp) if isinstance(mcp,dict) else [],'mcp_server_enabled':{n:v.get('enabled') for n,v in mcp.items() if isinstance(v,dict)} if isinstance(mcp,dict) else {},'canonical_features':{k:(features.get(k) if isinstance(features.get(k),bool) else {'type':type(features.get(k)).__name__,'enabled':features.get(k,{}).get('enabled') if isinstance(features.get(k),dict) and isinstance(features.get(k,{}).get('enabled'),bool) else None}) for k in ['hooks','plugins','remote_plugin','apps','memories','token_budget','goals','agent_message_board','guardianv2'] if k in features},'history_notes_condition':token.get('use_history_notes_extension') if isinstance(token,dict) else None,'hooks_event_counts':{k:len(v) for k,v in config.get('hooks',{}).items() if isinstance(v,list)} if isinstance(config.get('hooks'),dict) else {}}
def main():
 DEST.mkdir(exist_ok=True);receipt={'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'CURRENT structural facts only, not bound to historical R2 launch times','mdm_api':'CFPreferencesAppValueIsForced only; values are never requested','mdm_before':mdm_forced()}
 root=pathlib.Path(json.loads((OUT/'r2/run-state.json').read_text())['workspace'])/'approved workflow consumer project'
 rpc=RPC(root)
 try:
  data=rpc.call('config/read',{'includeLayers':True,'cwd':str(root)},timeout=30)
  receipt['config_read']={'success':True,'request':{'method':'config/read','includeLayers':True,'cwd':str(root)},'result_top_level_keys':sorted(data),'merged_structure':structural(data.get('config',{})),'layers':[]}
  for layer in data.get('layers') or []:
   cfg=layer.get('config',{})
   receipt['config_read']['layers'].append({'source':layer.get('name',layer.get('source')),'version':layer.get('version'),'disabled_reason':layer.get('disabledReason'),'structure':structural(cfg)})
  receipt['config_read']['all_layer_mcp_names']=sorted(set(receipt['config_read']['merged_structure']['mcp_server_names'])|{n for layer in receipt['config_read']['layers'] for n in layer['structure'].get('mcp_server_names',[])})
 except Exception as e:receipt['config_read']={'success':False,'error':str(e)}
 finally:rpc.close()
 receipt['mdm_after']=mdm_forced()
 (DEST/'current-structural-receipt.json').write_text(clean(json.dumps(receipt,ensure_ascii=False,indent=2))+'\n')
 print(json.dumps({'mdm_before':receipt['mdm_before'],'mdm_after':receipt['mdm_after'],'config_read_success':receipt['config_read'].get('success'),'merged_mcp_count':len(receipt['config_read'].get('merged_structure',{}).get('mcp_server_names',[])),'all_layer_mcp_count':len(receipt['config_read'].get('all_layer_mcp_names',[])),'receipt':str(DEST/'current-structural-receipt.json')},indent=2))
if __name__=='__main__':main()
