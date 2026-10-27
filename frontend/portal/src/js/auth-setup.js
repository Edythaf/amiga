// A launcher capability stays in memory. Remove it from the address bar immediately.
export function consumeOwnerSetup(location,history){
  if(location.pathname!=='/login'||!location.hash.startsWith('#owner-setup='))return '';
  const value=new URLSearchParams(location.hash.slice(1)).get('owner-setup')??'';
  history.replaceState(null,'',location.pathname+location.search);
  return /^[A-Za-z0-9_-]{43}$/.test(value)?value:'';
}
