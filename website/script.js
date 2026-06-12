const FEATURES = [
  {name:"Advanced Antinuke",tag:"Audit-Log Based",meta:"Core",desc:"Monitors every privileged Discord action through the audit log. Mass-deletes, role wipes, channel nukes — detected and reversed before they take hold."},
  {name:"Anti-Raid System",tag:"Join Rate Monitoring",meta:"Defense",desc:"Smart raid detection with configurable join-rate thresholds, account age filtering, and instant server lockdown on spike."},
  {name:"Complete Moderation",tag:"Full Command Suite",meta:"Moderation",desc:"Ban, kick, timeout, warn, purge, and case history. Everything your team needs in slash commands with role-gated permissions."},
  {name:"Smart AutoMod",tag:"Content Filtering",meta:"AutoMod",desc:"Spam detection, mention-flooding prevention, invite-link filtering, and customizable content thresholds per channel."},
  {name:"Comprehensive Logging",tag:"Rich Embed Logs",meta:"Logging",desc:"Every server event logged with full context — message edits, role changes, voice events — with searchable history."},
  {name:"Backup & Restore",tag:"Server Snapshots",meta:"Recovery",desc:"Scheduled snapshots of channels and roles. Recover from a full nuke in under two minutes with selective or full restoration."},
  {name:"Verification Gate",tag:"Custom Flows",meta:"Onboarding",desc:"Customizable verification with embed prompts, button interactions, and automatic role assignment for new members."},
  {name:"Whitelist System",tag:"Trusted Users",meta:"Trust",desc:"Granular permission tiers (1–3) for trusted admins and bots. Full immunity with audit-tracked overrides."},
]

const COMMANDS = [
  {name:"/setup",tag:"Wizard",meta:"Start",desc:"Interactive setup wizard — configures protection levels, logging channels, and default roles in one guided flow."},
  {name:"/antinuke enable",tag:"Protection",meta:"Antinuke",desc:"Activates antinuke protection with sensible defaults. Tune thresholds with /antinuke config."},
  {name:"/whitelist add @user",tag:"Trust",meta:"Whitelist",desc:"Grants a trusted user or bot antinuke immunity. Supports permission tiers 1–3."},
  {name:"/ban @user [reason]",tag:"Moderation",meta:"Mod",desc:"Bans a member, logs the case, and DMs the user automatically with an optional reason."},
  {name:"/purge [count]",tag:"Cleanup",meta:"Mod",desc:"Bulk-deletes up to 100 messages. Supports filtering by user or message type."},
  {name:"/restore",tag:"Recovery",meta:"Backup",desc:"Rebuilds deleted channels and roles from the last saved snapshot. Selective or full restore."},
  {name:"/antinuke config",tag:"Settings",meta:"Antinuke",desc:"Fine-tune detection thresholds, action modes, and whitelist tiers for your server's specific needs."},
  {name:"/logs setup",tag:"Logging",meta:"Logging",desc:"Configure log channels for moderation events, audit actions, join/leave, and message changes."},
]

const SPECS = [
  {name:"Response Latency",pct:98},{name:"Detection Accuracy",pct:99},
  {name:"Uptime",pct:99.9},{name:"Bypass Resistance",pct:100},
  {name:"Setup Speed",pct:95},{name:"Permission Coverage",pct:97},
  {name:"Logging Completeness",pct:94},{name:"Moderation Coverage",pct:96},
]

const TIMELINE = [
  {date:"Instant",role:"Threat Detected",company:"Audit-log event fires",desc:"Balance reads every Discord audit log entry in real time — before any client-side action can complete. Mass-delete starts? Caught at entry 1."},
  {date:"<200ms",role:"Action Analyzed",company:"Pattern matching engine",desc:"The event is matched against configured threat signatures. Threshold exceeded triggers an immediate response, bypassing all permission checks."},
  {date:"<500ms",role:"Perpetrator Punished",company:"Auto-enforcement",desc:"The offending user or bot is instantly stripped of permissions, banned, or quarantined depending on whitelist tier and configured action mode."},
  {date:"<1s",role:"Server Restored",company:"Snapshot recovery",desc:"Deleted channels, roles, and permissions are rebuilt from the most recent snapshot. Your server is back online before most admins notice."},
  {date:"Always",role:"Audit Logged",company:"Full transparency",desc:"Every automated action is logged with context — who triggered it, what was done, and what was reversed. Full accountability, zero black boxes."},
]

const TESTIMONIALS = [
  {quote:"Someone tried to nuke our 50k-member server. Balance caught it at the first deleted channel. Server was fully restored before I even woke up.",author:"Kael M.",role:"Community Owner"},
  {quote:"Set it up in under 5 minutes using /setup. It just works. The whitelist system is exactly what we needed for our own bots.",author:"Rina V.",role:"Server Admin"},
  {quote:"The logging alone is worth it. Every single audit event, beautifully formatted. We finally have full accountability in our moderation team.",author:"Dev T.",role:"Moderator"},
]

const FAQS = [
  {q:"How does antinuke work without being bypassable?",a:"Balance hooks directly into Discord's audit log, not permission checks. Any privileged action fires an audit event regardless of who or what performs it — including bots with Administrator. There's no permission-based bypass path because we don't rely on permissions to detect."},
  {q:"Will Balance accidentally punish my own bots or admins?",a:"No — the whitelist system (tiers 1–3) lets you grant full immunity to trusted users and bots. Actions taken by whitelisted entities are logged but not acted upon. Run /whitelist add before enabling strict thresholds."},
  {q:"What happens when a nuke is detected mid-execution?",a:"Balance issues an immediate stop-action: the perpetrator is quarantined within <200ms, further actions are blocked, and the restore engine begins rebuilding from snapshot. Most nukes are contained within 1–3 deleted channels."},
  {q:"How do I set up Balance for the first time?",a:"Run /setup. The interactive wizard walks you through protection level, logging channels, whitelist configuration, and verification setup. Most servers are fully configured in under 5 minutes."},
  {q:"Does Balance store any message content?",a:"No. Balance only processes metadata (user IDs, channel IDs, permission states, audit log entries) for security purposes. Message content is never stored. Security logs are retained for 30 days by default."},
  {q:"Can I customize detection thresholds?",a:"Yes — /antinuke config exposes every threshold: max channel deletes per minute, max role deletions, join rate limits, and more. Tune them to match your server size and moderation style."},
]

const QUICK_CHIPS = [
  {label:'Setup',msg:'How do I set up Balance for the first time?'},
  {label:'Antinuke',msg:'How does the antinuke system work?'},
  {label:'Commands',msg:'What are the most important commands?'},
  {label:'Whitelist',msg:'How does the whitelist system work?'},
]

function now(){return new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}

function goTo(id,e){
  if(e)e.preventDefault()
  const wipe=document.getElementById('wipe')
  wipe.className='in'
  setTimeout(()=>{
    document.getElementById(id)?.scrollIntoView({behavior:'instant'})
    wipe.className='out'
    setTimeout(()=>{wipe.className=''},450)
  },450)
}

function initFog(){
  const C=document.getElementById('fog'),ctx=C.getContext('2d')
  let W,H,frame=0,t=0,mx=.5,my=.5,tmx=.5,tmy=.5,sy=0,syt=0,raf
  const resize=()=>{W=C.width=window.innerWidth;H=C.height=window.innerHeight}
  resize();window.addEventListener('resize',resize)
  window.addEventListener('mousemove',e=>{tmx=e.clientX/W;tmy=e.clientY/H})
  window.addEventListener('scroll',()=>{sy=window.scrollY})
  const B=Array.from({length:6},(_,i)=>({phase:(i/6)*Math.PI*2,spd:.055+i*.007,cx:.15+(i/5)*.7,cy:.1+(i/5)*.8,orx:.22+(i%3)*.06,ory:.18+(i%2)*.1,size:.30+(i%3)*.09,alpha:.03+(i%3)*.007}))
  const P=Array.from({length:55},()=>({x:Math.random()*1920,y:Math.random()*1080,vx:(Math.random()-.5)*.18,vy:(Math.random()-.5)*.14,r:Math.random()*1.4+.3,a:Math.random()*.12+.03}))
  const draw=()=>{
    raf=requestAnimationFrame(draw);if(++frame%2!==0)return
    mx+=(tmx-mx)*.035;my+=(tmy-my)*.035;syt+=(sy-syt)*.06
    ctx.clearRect(0,0,W,H)
    for(const b of B){
      const bx=(b.cx+Math.sin(t*b.spd+b.phase)*b.orx)*W
      const by=(b.cy+Math.cos(t*b.spd*.8+b.phase)*b.ory)*H-syt*.05
      const br=W*b.size*(1+.06*Math.sin(t*.25+b.phase))
      const g=ctx.createRadialGradient(bx,by,0,bx,by,br)
      g.addColorStop(0,`rgba(100,100,95,${b.alpha})`)
      g.addColorStop(.5,`rgba(90,90,85,${b.alpha*.3})`)
      g.addColorStop(1,'rgba(0,0,0,0)')
      ctx.fillStyle=g;ctx.fillRect(0,0,W,H)
    }
    for(const p of P){
      p.x+=p.vx;p.y+=p.vy
      if(p.x<0)p.x=W;if(p.x>W)p.x=0;if(p.y<0)p.y=H;if(p.y>H)p.y=0
      const dx=mx*W-p.x,dy=my*H-p.y,d=Math.sqrt(dx*dx+dy*dy)
      if(d<180){p.vx+=dx/d*.008;p.vy+=dy/d*.008}
      p.vx*=.99;p.vy*=.99
      ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2)
      ctx.fillStyle=`rgba(80,80,75,${p.a})`;ctx.fill()
    }
    const gx=mx*W,gy=my*H
    const g1=ctx.createRadialGradient(gx,gy,0,gx,gy,W*.26)
    g1.addColorStop(0,'rgba(80,80,75,0.06)');g1.addColorStop(.5,'rgba(60,60,55,0.02)');g1.addColorStop(1,'rgba(0,0,0,0)')
    ctx.fillStyle=g1;ctx.fillRect(0,0,W,H)
    t+=.014
  }
  draw()
}

function initCursor(){
  const cr=document.getElementById('cur'),rr=document.getElementById('cur-ring')
  let cx=0,cy=0,rx=0,ry=0,raf
  window.addEventListener('mousemove',e=>{cx=e.clientX;cy=e.clientY;cr.style.left=cx+'px';cr.style.top=cy+'px'})
  const loop=()=>{raf=requestAnimationFrame(loop);rx+=(cx-rx)*.11;ry+=(cy-ry)*.11;rr.style.left=rx+'px';rr.style.top=ry+'px'}
  loop()
  const addHover=()=>{
    document.querySelectorAll('a,button,.fq,.testi-btn,.copy-btn,.invite-btn,.secondary-btn,.qchip,.qr-btn,.chat-send,.clear-btn,.chat-input').forEach(el=>{
      el.addEventListener('mouseenter',()=>{cr.classList.add('h');rr.classList.add('h')})
      el.addEventListener('mouseleave',()=>{cr.classList.remove('h');rr.classList.remove('h')})
    })
  }
  addHover()
  new MutationObserver(addHover).observe(document.body,{childList:true,subtree:true})
  window.addEventListener('click',e=>{
    cr.classList.add('ck');setTimeout(()=>cr.classList.remove('ck'),200)
    const d=document.createElement('div');d.className='rip'
    d.style.cssText=`width:80px;height:80px;left:${e.clientX}px;top:${e.clientY}px`
    document.body.appendChild(d);setTimeout(()=>d.remove(),650)
  })
}

function renderFeatures(){
  const ul=document.getElementById('features-list')
  FEATURES.forEach((f,i)=>{
    ul.innerHTML+=`<div class="reveal" data-delay="${i*.04}"><li class="pi">
      <div class="plink" style="cursor:default">
        <span class="pname">${f.name}</span>
        <span class="ptag">${f.tag}</span>
        <span class="pmeta">${f.meta}</span>
      </div>
    </li></div>`
  })
}

function renderCommands(){
  const ul=document.getElementById('commands-list')
  COMMANDS.forEach((c,i)=>{
    ul.innerHTML+=`<div class="reveal" data-delay="${i*.04}"><li class="pi">
      <div class="plink" style="cursor:default">
        <span class="pname" style="font-family:monospace;font-size:clamp(12px,1.5vw,16px)">${c.name}</span>
        <span class="ptag">${c.tag}</span>
        <span class="pmeta">${c.meta}</span>
      </div>
    </li></div>`
  })
}

function renderSpecs(){
  const g=document.getElementById('specs-grid')
  SPECS.forEach((s,i)=>{
    const d=document.createElement('div')
    d.className='skill-row reveal';d.dataset.delay=i*.07
    d.innerHTML=`<div class="skill-top"><span>${s.name}</span><span class="skill-pct">${s.pct}%</span></div><div class="skill-track"><div class="skill-fill" style="--w:${s.pct}%"></div></div>`
    g.appendChild(d)
  })
}

function renderTimeline(){
  const tl=document.getElementById('timeline')
  TIMELINE.forEach((t,i)=>{
    const d=document.createElement('div')
    d.className='tl-item reveal';d.dataset.delay=i*.12
    d.innerHTML=`<div class="tl-dot"></div><div class="tl-date">${t.date}</div><div class="tl-role">${t.role}</div><div class="tl-co">${t.company}</div><div class="tl-desc">${t.desc}</div>`
    tl.appendChild(d)
  })
}

function renderTestimonials(){
  let idx=0
  const track=document.getElementById('testi-track')
  const dots=document.getElementById('tdots')
  TESTIMONIALS.forEach((t,i)=>{
    track.innerHTML+=`<div class="testi-slide"><div class="testi-quote">"${t.quote}"</div><div class="testi-author"><strong>${t.author}</strong>${t.role}</div></div>`
    dots.innerHTML+=`<div class="tdot${i===0?' on':''}" data-i="${i}"></div>`
  })
  const update=()=>{
    track.style.transform=`translateX(-${idx*100}%)`
    document.querySelectorAll('.tdot').forEach((d,i)=>d.classList.toggle('on',i===idx))
  }
  document.getElementById('testi-prev').addEventListener('click',()=>{idx=(idx-1+TESTIMONIALS.length)%TESTIMONIALS.length;update()})
  document.getElementById('testi-next').addEventListener('click',()=>{idx=(idx+1)%TESTIMONIALS.length;update()})
}

function renderFAQ(){
  const ul=document.getElementById('faq-list')
  FAQS.forEach((f,i)=>{
    ul.innerHTML+=`<li class="fi"><div class="fq" data-faq="${i}">${f.q}<span class="ftog">+</span></div><div class="fans">${f.a}</div></li>`
  })
  ul.addEventListener('click',e=>{
    const fq=e.target.closest('.fq');if(!fq)return
    const fi=fq.parentElement
    const wasOpen=fi.classList.contains('open')
    document.querySelectorAll('.fi.open').forEach(el=>el.classList.remove('open'))
    if(!wasOpen)fi.classList.add('open')
  })
}

function initChat(){
  const msgsEl=document.getElementById('chat-msgs')
  const inputEl=document.getElementById('chat-input')
  const sendBtn=document.getElementById('chat-send')
  const clearBtn=document.getElementById('clear-chat')
  const qrRow=document.getElementById('qr-row')
  const quickChips=document.getElementById('quick-chips')
  let history=[],loading=false

  QUICK_CHIPS.forEach(c=>{
    const btn=document.createElement('button')
    btn.className='qchip';btn.textContent=c.label
    btn.addEventListener('click',()=>send(c.msg))
    quickChips.appendChild(btn)
  })

  setTimeout(()=>{
    addMsg('bot',"Hey! I'm BalanceAI — the assistant for the Balance Discord antinuke bot. Ask me anything about setup, features, commands, or protection levels.")
    showQR([
      {label:'Setup',msg:'How do I set up Balance?'},
      {label:'Antinuke',msg:'How does antinuke work?'},
      {label:'Commands',msg:'What commands are available?'},
      {label:'Whitelist',msg:'How does the whitelist work?'},
    ])
  },400)

  function addMsg(role,text){
    const div=document.createElement('div')
    div.className=`chat-msg ${role}`
    div.innerHTML=`<div class="chat-bubble">${text}</div><div class="chat-time">${now()}</div>`
    msgsEl.appendChild(div)
    msgsEl.scrollTop=msgsEl.scrollHeight
  }

  function addTyping(){
    const div=document.createElement('div')
    div.className='chat-msg bot';div.id='typing'
    div.innerHTML=`<div class="chat-bubble"><div class="typing-dots"><span></span><span></span><span></span></div></div>`
    msgsEl.appendChild(div)
    msgsEl.scrollTop=msgsEl.scrollHeight
  }

  function removeTyping(){const t=document.getElementById('typing');if(t)t.remove()}

  function showQR(items){
    qrRow.style.display='flex';qrRow.innerHTML=''
    items.forEach(item=>{
      const btn=document.createElement('button');btn.className='qr-btn';btn.textContent=item.label
      btn.addEventListener('click',()=>send(item.msg));qrRow.appendChild(btn)
    })
  }

  function hideQR(){qrRow.style.display='none';qrRow.innerHTML=''}

  async function send(text){
    if(!text.trim()||loading)return
    addMsg('user',text)
    history.push({role:'user',content:text})
    inputEl.value='';hideQR();loading=true;addTyping()
    try{
      const res=await fetch('https://api.anthropic.com/v1/messages',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          model:'claude-sonnet-4-20250514',
          max_tokens:1000,
          system:`You are BalanceAI, the official AI assistant for Balance — a Discord antinuke and security bot. Answer questions about Balance's features, commands, setup, protection system, whitelist, and moderation tools. Keep answers concise and helpful. Key facts: Balance uses audit-log based detection (impossible to bypass), has /setup wizard, whitelist tiers 1-3, antinuke, anti-raid, AutoMod, backup/restore, verification, logging. Response time <0.2s, 99% detection rate, 0 known bypasses, 24/7 protection. The invite link is https://discord.com/api/oauth2/authorize?client_id=YOUR_BOT_ID&permissions=8&scope=bot%20applications.commands`,
          messages:history
        })
      })
      const data=await res.json()
      const reply=data.content?.[0]?.text||"I'm having trouble responding right now. Please check the support server!"
      history.push({role:'assistant',content:reply})
      removeTyping();addMsg('bot',reply)
      const l=reply.toLowerCase()
      if(l.includes('setup')||l.includes('install')){
        showQR([{label:'First Command',msg:'What is the first command I should run?'},{label:'Permissions',msg:'What permissions does Balance need?'},{label:'Channels',msg:'How do I set up logging channels?'}])
      } else if(l.includes('antinuke')||l.includes('nuke')){
        showQR([{label:'Thresholds',msg:'How do I configure detection thresholds?'},{label:'Actions',msg:'What actions does antinuke take?'},{label:'Whitelist',msg:'How do I whitelist my own bots?'}])
      } else if(l.includes('command')){
        showQR([{label:'Moderation',msg:'What moderation commands are available?'},{label:'Config',msg:'What configuration commands exist?'},{label:'Recovery',msg:'How do I use /restore?'}])
      } else {
        showQR([{label:'More Info',msg:'Tell me more about that'},{label:'Setup',msg:'How do I get started?'},{label:'Commands',msg:'What commands are available?'}])
      }
    }catch(err){
      removeTyping();addMsg('bot',"Connection issue — please check the support server for help!")
      showQR([{label:'Try Again',msg:text},{label:'Setup',msg:'How do I set up Balance?'}])
    }
    loading=false
  }

  sendBtn.addEventListener('click',()=>send(inputEl.value))
  inputEl.addEventListener('keydown',e=>{if(e.key==='Enter')send(inputEl.value)})
  clearBtn.addEventListener('click',()=>{
    msgsEl.innerHTML='';history=[];hideQR()
    setTimeout(()=>{
      addMsg('bot',"Chat cleared! Ask me anything about Balance.")
      showQR([{label:'Setup',msg:'How do I set up Balance?'},{label:'Antinuke',msg:'How does antinuke work?'}])
    },200)
  })
}

function initProgress(){
  const bar=document.getElementById('prog')
  window.addEventListener('scroll',()=>{
    const h=document.documentElement.scrollHeight-window.innerHeight
    bar.style.width=(h>0?(window.scrollY/h)*100:0)+'%'
  })
}

function initBTT(){
  const btn=document.getElementById('btt')
  window.addEventListener('scroll',()=>btn.classList.toggle('show',window.scrollY>400))
  btn.addEventListener('click',()=>window.scrollTo({top:0,behavior:'smooth'}))
}

function initNav(){
  const links=document.querySelectorAll('[data-nav]')
  const obs=new IntersectionObserver(entries=>{
    entries.forEach(e=>{
      if(e.isIntersecting){
        links.forEach(l=>l.classList.toggle('on',l.dataset.nav===e.target.id))
      }
    })
  },{threshold:.35})
  document.querySelectorAll('section[id]').forEach(s=>obs.observe(s))

  links.forEach(l=>{
    l.addEventListener('click',e=>{
      const id=l.dataset.nav;if(id){goTo(id,e)}
      document.getElementById('mobmenu')?.classList.remove('open')
      document.getElementById('hbg')?.classList.remove('open')
    })
  })
}

function initReveal(){
  const obs=new IntersectionObserver(entries=>{
    entries.forEach(e=>{
      if(e.isIntersecting){
        const delay=parseFloat(e.target.dataset.delay||0)
        e.target.style.transitionDelay=delay+'s'
        e.target.classList.add('vis')
        e.target.querySelectorAll('.skill-fill').forEach(f=>{
          setTimeout(()=>f.classList.add('go'),delay*1000)
        })
        obs.unobserve(e.target)
      }
    })
  },{threshold:.08})
  document.querySelectorAll('.reveal').forEach(el=>obs.observe(el))
}

function initParallax(){
  const hc=document.getElementById('hero-content')
  if(!hc)return
  window.addEventListener('scroll',()=>{hc.style.transform=`translateY(${window.scrollY*.28}px)`},{passive:true})
}

function initMobile(){
  const hbg=document.getElementById('hbg'),mob=document.getElementById('mobmenu')
  if(hbg)hbg.addEventListener('click',()=>{hbg.classList.toggle('open');mob.classList.toggle('open')})
}

function initCopy(){
  const btn=document.getElementById('copy-invite')
  btn.addEventListener('click',()=>{
    navigator.clipboard.writeText('https://discord.com/api/oauth2/authorize?client_id=YOUR_BOT_ID&permissions=8&scope=bot%20applications.commands')
      .then(()=>{btn.textContent='✓ Copied!';btn.classList.add('copied');setTimeout(()=>{btn.textContent='Copy Invite Link';btn.classList.remove('copied')},2000)})
  })
}

document.addEventListener('click',e=>{
  const a=e.target.closest('a[href^="#"]')
  if(a&&!a.dataset.nav){
    const id=a.getAttribute('href').slice(1)
    goTo(id,e)
  }
})

initFog()
initCursor()
renderFeatures()
renderCommands()
renderSpecs()
renderTimeline()
renderTestimonials()
renderFAQ()
initProgress()
initBTT()
initMobile()
initCopy()
initChat()

setTimeout(()=>{
  const splash=document.getElementById('splash')
  splash.classList.add('hide')
  setTimeout(()=>{
    splash.remove()
    const wrap=document.getElementById('wrap')
    wrap.style.display='block'
    initNav()
    initReveal()
    initParallax()
  },900)
},2100)