// 前端页面冒烟测试：node --experimental-default-type=module test_frontend.mjs
// 用真实 store/pages 模块渲染日加权剖面页，验证表单、任务列表与剖面明细的关键内容。
import {store} from '/workspace/frontend/src/stores/business.js';
import {profilesPage} from '/workspace/frontend/src/pages/profiles.js';

let passed=0;
function check(name,cond,info=''){if(!cond){console.error('FAIL',name,info);process.exit(1);}passed++;console.log(' ✓',name);}

store.user={email:'operator@operator.local',role:'operator'};
store.plans=[{id:1,name:'跨午夜剖面基线',dataset_id:4,steps:[{op:'scan',source:'readings'}],note:''},{id:2,name:'过滤-连接-分组基线',dataset_id:1,steps:[{op:'scan',source:'readings'},{op:'group',keys:['zone'],measure:'value',aggregate:'avg'}],note:''}];
store.traces=[];
const result={timezone:'Asia/Shanghai',start_date:'2026-11-17',end_date:'2026-11-18',gap_seconds:3600,batch_limit:500,batches:2,days:[{date:'2026-11-17',day_seconds:86400.0,reconciled:true,sensors:[{sensor_id:1,coverage_seconds:7200.0,weighted_mean:20.0},{sensor_id:2,coverage_seconds:0.0,weighted_mean:null}]}],sensors:[{sensor_id:1,zone:'北场',device_type:'pump',coverage_seconds:10800.0,covered_days:2,weighted_mean:25.0},{sensor_id:2,zone:'南场',device_type:'motor',coverage_seconds:0.0,covered_days:0,weighted_mean:null}],totals:{days:2,reconciled_days:2,sensors:2,selected_rows:12,collapsed_instants:11},source:{dataset:'松原跨午夜采样',plan:'跨午夜剖面基线'},duration_ms:3.2,checksum:'abc123'};
store.profiles=[{id:7,name:'daily-profile',plan_id:1,dataset_id:4,tz:'Asia/Shanghai',start_date:'2026-11-17',end_date:'2026-11-18',status:'completed',result,error:null,checkpoint:{reconciled_days:2,total_days:2},created_at:'2026-11-20T09:35:00'},{id:8,name:'running-one',plan_id:1,dataset_id:4,tz:'UTC',start_date:'2026-11-17',end_date:'2026-11-17',status:'running',result:null,error:null,checkpoint:{reconciled_days:0,total_days:1},created_at:'2026-11-20T09:36:00'}];

const html=profilesPage(7);
check('渲染表单-起止日与时区',html.includes('name="start_date"')&&html.includes('name="end_date"')&&html.includes('name="timezone"')&&html.includes('Asia/Shanghai'));
check('含group计划被禁用',html.includes('含 group 不可剖面')&&html.includes('disabled'));
check('任务列表-核齐进度',html.includes('2/2 天'));
check('剖面明细-设备覆盖时长',html.includes('3.00 h')&&html.includes('10800'));
check('剖面明细-设备均值',html.includes('<b>25</b>'));
check('零覆盖显示空均值',html.includes('—'));
check('逐日明细-实际日长',html.includes('实际日长 24.00 h'));
check('导出按钮',html.includes('data-export="/profiles/7/export"'));
check('受理版来源',html.includes('松原跨午夜采样')&&html.includes('跨午夜剖面基线'));

const running=profilesPage(8);
check('执行中提示断点恢复',running.includes('还在逐日核齐')&&running.includes('0/1'));

store.profiles=[];
check('空状态不报错',profilesPage(null).includes('剖面任务'));
console.log(`全部通过：${passed}项`);
