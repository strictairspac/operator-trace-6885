import {datasets,plans,traces,profiles} from '../api/business.js';
export const store={datasets:[],plans:[],traces:[],profiles:[],user:null};
export async function refresh(){[store.datasets,store.plans,store.traces,store.profiles]=await Promise.all([datasets.list(),plans.list(),traces.list(),profiles.list()]);}
