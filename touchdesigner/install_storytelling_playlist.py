r"""3080-only offline playlist installer. Run in TouchDesigner Python Textport.

exec(open(r'C:\...\touchdesigner\install_storytelling_playlist.py', encoding='utf-8').read())
install(); audit()
Save with native File > Save As to a NEW file; this script never saves a TOE.
"""
import json
import math
from pathlib import Path
import re

ROOT = Path(project.folder).resolve()


def _resolve_playlist_work(root, manifest_path):
    root = Path(root).resolve()
    path = (root/manifest_path).resolve()
    parent = root/'work/storytelling-real-december'
    if path.name != 'playlist.json' or not path.parent.is_relative_to(parent) or path.parent == parent:
        raise ValueError('Use a dedicated project-local storytelling playlist manifest')
    return path.parent


def _playlist_work():
    connector = op('/project1/podcast_visualizer')
    parameter = getattr(connector.par, 'Playlistmanifest', None) if connector is not None else None
    selected = str(parameter.eval()) if parameter is not None else ''
    # Older .26 projects intentionally continue to use the original 35 stories.
    return _resolve_playlist_work(ROOT, selected or
        'work/storytelling-real-december/playlist-35-2026-10-29/playlist.json')


WORK = _playlist_work()


def _connector():
    if (str(app.build) != '2025.32820' or
        re.fullmatch(r'podcast(?:\.3080)?(?:\.\d+)?\.toe', str(project.name), re.I) is None):
        raise RuntimeError('This installer accepts only the 3080 podcast project in TD 2025.32820')
    connector = op('/project1/podcast_visualizer')
    if connector is None or not (WORK/'playlist.json').exists():
        raise RuntimeError('Existing connector and validated playlist required')
    for name in ('StreamDiffusionTD', 'StreamDiffusionTD2'):
        target = connector.op(name)
        if target is not None and (bool(target.par.Serveractive.eval()) or bool(target.par.Streamactive.eval())):
            raise RuntimeError('Stop both model servers before this offline installation/audit')
    return connector


def _manifest():
    return json.loads((WORK/'playlist.json').read_text(encoding='utf-8'))


def _controller():
    return op('/project1/podcast_visualizer/execute_callbacks').module.get_controller()


def jump_story(number):
    connector = op('/project1/podcast_visualizer')
    control = connector.op('show_control')
    seq = _controller().sequencer
    story = next(s for s in seq.stories if s['number'] == int(number))
    # ceil prevents a frame-quantized seek showing the previous person's image.
    frame = math.ceil(story['start_ms']/1000*project.cookRate)+1
    playing = bool(control.par.Play.eval())
    op('/project1').time.frame = frame
    op('/local/time').par.play = playing
    _controller().update(float(connector.par.Playheadsec.eval()))
    return story


def navigate(delta):
    connector = op('/project1/podcast_visualizer')
    control = connector.op('show_control')
    seq = _controller().sequencer
    ms = seq.navigate(float(connector.par.Playheadsec.eval())*1000, delta,
                      loop=bool(control.par.Loopplaylist.eval()))
    return jump_story(seq.story_at(ms)['number'])


def configure_loop():
    control = op('/project1/podcast_visualizer/show_control')
    op('/local/time').par.rangelimit = 'loop' if bool(control.par.Loopplaylist.eval()) else 'hold'


def _add(page, comp, kind, name, label):
    current = getattr(comp.par, name, None)
    return current if current is not None else getattr(page, 'append'+kind)(name, label=label)[0]


def install(manifest_path=None):
    global WORK
    if manifest_path is not None:
        WORK = _resolve_playlist_work(ROOT, manifest_path)
    connector = _connector()
    data = _manifest()
    control = connector.op('show_control')
    # Do not rebuild Show Control or either paid component.
    connector.par.Enabled = False
    control.par.Play = False
    op('/local/time').par.play = False
    control.par.Audioenabled = False
    connector.op('audio_out').par.active = False
    connector.par.Runtimeprofile = '3080_safe'
    control.par.Runtimeprofile = '3080_safe'
    control.par.Livevariations = False
    control.par.Runtimeprofile.readOnly = True
    control.par.Livevariations.readOnly = True
    for name in ('story_proof_callbacks',):
        previous = control.op(name)
        if previous is not None:
            previous.par.active = False
    if getattr(control.par, 'Proofstory', None) is not None:
        control.par.Proofstory.readOnly = True
        control.par.Proofstory.label = 'Legacy .25 Test (Disabled)'
    control.op('control_callbacks').text = (ROOT/'touchdesigner/show_control_callbacks.py').read_text(encoding='utf-8')
    connector.op('execute_callbacks').text = (ROOT/'touchdesigner/execute_callbacks.py').read_text(encoding='utf-8')
    connector.par.Sequencermodule = str(ROOT/'touchdesigner/storytelling_playlist_sequencer.py')
    for name, mode in (('Scenejson','original'), ('Humanfigurejson','human_figures'), ('Balancedjson','balanced')):
        getattr(connector.par, name).val = str(ROOT/data['plans'][mode]['path'])
    connector.par.Canonicalvisuals = str(connector.par.Scenejson.eval())
    connector.par.Canonicalhumanvisuals = str(connector.par.Humanfigurejson.eval())
    podcast_page = next(p for p in connector.customPages if p.name == 'Podcast')
    manifest_parameter = _add(podcast_page, connector, 'File', 'Playlistmanifest', 'Reviewed Playlist Manifest')
    manifest_parameter.val = str(WORK/'playlist.json')
    manifest_parameter.readOnly = True
    _add(podcast_page, connector, 'File', 'Combinedaudiofile', 'Narration + Ambient Audio')
    for comp in (connector, control):
        comp.par.Audiosource.menuNames = ['voices', 'soundscape', 'combined']
        comp.par.Audiosource.menuLabels = ['Narration Only', 'Ambient Only', 'Narration + Ambient']
    help_table = control.op('controls')
    if help_table is not None:
        for row in range(1, help_table.numRows):
            if str(help_table[row,0]) == 'Audio Source':
                help_table[row,1] = 'Narration Only, Ambient Only, or Narration + Ambient on the same locked clock'
        playlist_help = f'{data["story_count"]} reviewed stories; next/previous/jump retain play state; edge fades never preview another memory'
        playlist_rows = [row for row in range(1,help_table.numRows) if str(help_table[row,0]) == 'Playlist']
        if playlist_rows:
            for row in playlist_rows:
                help_table[row,1] = playlist_help
        else:
            help_table.appendRow(['Playlist',playlist_help])
    for parameter, kind in (('Audiofile','voices_only'), ('Soundscapeaudiofile','soundscape_only'), ('Combinedaudiofile','combined')):
        getattr(connector.par, parameter).val = str(ROOT/data['audio'][kind])
    for name, parameter in (('voices_only_audio','Audiofile'), ('soundscape_audio','Soundscapeaudiofile'), ('combined_audio','Combinedaudiofile')):
        node = connector.op(name)
        if node is None:
            node = connector.create(audiofileinCHOP, name)
            node.comment = 'Recovered Homes offline reviewed storytelling playlist audio'
            node.nodeX, node.nodeY = 0, -400
        node.par.file.expr = f'parent().par.{parameter}'
        node.par.file.mode = ParMode.EXPRESSION
        node.par.playmode = 'locked'
        node.par.play = True
        node.par.repeat = False
    source_switch = connector.op('audiosource_switch')
    for index, name in enumerate(('voices_only_audio','soundscape_audio','combined_audio')):
        source_switch.inputConnectors[index].disconnect()
        connector.op(name).outputConnectors[0].connect(source_switch.inputConnectors[index])
    page = next((p for p in control.customPages if p.name == 'Playlist'), None)
    if page is None:
        page = control.appendCustomPage('Playlist')
    selector = _add(page, control, 'Menu', 'Storychoice', 'Jump to Story')
    selector.menuNames = [f'story{s["number"]}' for s in data['stories']]
    selector.menuLabels = [f'{s["number"]:02d}. {s["title"]}' for s in data['stories']]
    for name, label in (('Previousstory','Previous Story'), ('Nextstory','Next Story'), ('Restartplaylist','Restart Playlist (Pause)')):
        _add(page, control, 'Pulse', name, label)
    _add(page, control, 'Toggle', 'Loopplaylist', 'Loop Full Playlist')
    fade = _add(page, control, 'Float', 'Storyfadesec', 'Story Edge Fade Seconds')
    fade.min, fade.max, fade.normMin, fade.normMax = 0, 15, 0, 5
    fade.clampMin = fade.clampMax = True
    seq_expression = "parent().op('execute_callbacks').module.get_controller().sequencer"
    now_expression = 'parent().par.Playheadsec.eval()*1000'
    current_expression = f'{seq_expression}.story_at({now_expression})'
    fields = (
        ('Str','Currentstory','Now Playing',f"str({current_expression}['number'])+' / {data['story_count']} — '+{current_expression}['title']"),
        ('Float','Storyelapsed','Story Elapsed Seconds',f"max(0,({now_expression}-{current_expression}['start_ms'])/1000)"),
        ('Float','Storyduration','Story Duration Seconds',f"{current_expression}['duration_ms']/1000"),
        ('Float','Playlistelapsed','Playlist Elapsed Seconds','parent().par.Playheadsec.eval()'),
    )
    for kind, name, label, expression in fields:
        par = _add(page, control, kind, name, label)
        par.expr, par.mode, par.readOnly = expression, ParMode.EXPRESSION, True
    callbacks = control.op('playlist_callbacks')
    if callbacks is None:
        callbacks = control.create(parameterexecuteDAT, 'playlist_callbacks')
    callbacks.par.active = False
    callbacks.par.op = control.path
    callbacks.par.pars = 'Storychoice Previousstory Nextstory Restartplaylist Loopplaylist'
    callbacks.par.valuechange = True
    callbacks.par.valueschanged = False
    callbacks.par.onpulse = True
    helper = str(ROOT/'touchdesigner/install_storytelling_playlist.py')
    callbacks.text = (
        f"exec(compile(open({helper!r},encoding='utf-8').read(),{helper!r},'exec'),globals())\n"
        "def onValueChange(par,prev):\n"
        "    if par.name=='Storychoice': jump_story(int(str(par.eval()).removeprefix('story')))\n"
        "    elif par.name=='Loopplaylist': configure_loop()\n"
        "def onPulse(par):\n"
        "    if par.name=='Nextstory': navigate(1)\n"
        "    elif par.name=='Previousstory': navigate(-1)\n"
        "    elif par.name=='Restartplaylist':\n"
        "        parent().par.Play=False\n"
        "        _controller().advance_seed_loop()\n"
        "        jump_story(1)\n"
    )
    control.par.Storychoice = 'story1'
    control.par.Loopplaylist = True
    control.par.Storyfadesec = 1.0
    configure_loop()
    end = math.ceil(data['duration_ms']/1000*project.cookRate)+1
    clock = op('/local/time')
    for name in ('start','rangestart'):
        getattr(clock.par,name).val = 1
    for name in ('end','rangeend'):
        getattr(clock.par,name).val = end
    connector.par.Playheadsec.expr = 'max(0, me.time.seconds)'
    connector.par.Playheadsec.mode = ParMode.EXPRESSION
    op('/project1').time.frame = 1
    control.par.Visualpath = connector.par.Visualpath = 'balanced'
    control.par.Audiosource = connector.par.Audiosource = 'combined'
    control.par.Crossfadesec = 8
    control.par.Randomseeds = False
    connector.op('execute_callbacks').module._CONTROLLER = None
    connector.par.Enabled = True
    controller = _controller()
    controller.reload()
    connector.par.Currentnarrationid.expr = "me.op('execute_callbacks').module.get_controller().sequencer.story_at(me.par.Playheadsec.eval()*1000)['narration_id']"
    connector.par.Currentnarrationid.mode = ParMode.EXPRESSION
    for index in (1,2):
        edge = connector.op(f'story_edge_fade_{index}')
        if edge is None:
            raise RuntimeError('Expected .25 story edge nodes; do not rebuild paid components')
        expression = ("parent().op('execute_callbacks').module.get_controller().sequencer.output_opacity_at("
                      "parent().par.Playheadsec.eval()*1000,parent().op('show_control').par.Storyfadesec.eval()*1000)")
        for parameter in ('brightness1','opacity'):
            getattr(edge.par,parameter).expr = expression
            getattr(edge.par,parameter).mode = ParMode.EXPRESSION
    control.par.Audioenabled = True
    connector.op('execute_callbacks').module._synchronize_show_control()
    control.op('control_callbacks').module._write_live_control()
    callbacks.par.active = True
    control.par.pageindex = next(i for i,p in enumerate(control.customPages) if p.name=='Playlist')
    print('PLAYLIST_INSTALLED', dict(stories=data['story_count'], duration_ms=data['duration_ms'],
          audio_modes=3, visual_modes=3, saved=False, servers_started=False))


def audit(saved=False, expected_project=None):
    connector = _connector()
    control = connector.op('show_control')
    data = _manifest()
    checks = []
    def check(label, condition):
        checks.append(dict(check=label, passed=bool(condition)))
    if saved:
        check('saved paused', not bool(control.par.Play.eval()) and not bool(op('/local/time').par.play.eval()))
        check('saved combined mode', str(control.par.Audiosource.eval())=='combined')
        check('saved balanced mode', str(control.par.Visualpath.eval())=='balanced')
        check('saved audio enabled', bool(control.par.Audioenabled.eval()))
        check('saved story fade', abs(float(control.par.Storyfadesec.eval())-1)<.0001)
        check('saved scene fade', abs(float(control.par.Crossfadesec.eval())-8)<.0001)
        check('saved fixed image seeds', not bool(control.par.Randomseeds.eval()))
        check('saved menu matches story count', len(control.par.Storychoice.menuNames)==data['story_count'])
        check('saved timeline length', int(op('/local/time').par.rangeend.eval())==math.ceil(data['duration_ms']/1000*project.cookRate)+1)
        check('saved playlist sequencer', Path(str(connector.par.Sequencermodule.eval())).resolve()==(ROOT/'touchdesigner/storytelling_playlist_sequencer.py').resolve())
    control.par.Play = False
    control.par.Audioenabled = False
    callbacks = connector.op('execute_callbacks').module
    callbacks._synchronize_show_control()
    audio_files = [str(connector.op(n).par.file.eval()) for n in ('voices_only_audio','soundscape_audio','combined_audio')]
    for mode in ('original','human_figures','balanced'):
        control.par.Visualpath = connector.par.Visualpath = mode
        controller = _controller()
        controller.reload()
        check(mode+': correct total', controller.sequencer.duration_ms == data['duration_ms'])
        check(mode+': correct scene JSON', Path(controller._selected_scene_path()).resolve()==(ROOT/data['plans'][mode]['path']).resolve())
        check(mode+': story count', len(controller.sequencer.stories)==data['story_count'])
        check(mode+': captions', len(controller.sequencer.captions)==data['plans'][mode]['captions'])
        check(mode+': scenes', len(controller.sequencer.scenes)==data['plans'][mode]['scenes'])
        for story in data['stories']:
            jump_story(story['number'])
            ms = float(connector.par.Playheadsec.eval())*1000
            frame = controller.sequencer.at(ms, crossfade_ms=30000)
            check(f'{mode}:{story["number"]}: correct memory', all(p.scene_id.startswith(story['narration_id']+'--') for p in frame.prompt_layers))
            check(f'{mode}:{story["number"]}: no previous fade', frame.crossfade_ms==0)
            check(f'{mode}:{story["number"]}: frame bound', story['start_ms']<=ms<story['start_ms']+1000/project.cookRate+1)
            check(f'{mode}:{story["number"]}: now playing', str(control.par.Currentstory.eval()).startswith(str(story['number'])+' /'))
            for source, index in (('voices',0), ('soundscape',1), ('combined',2)):
                before = float(connector.par.Playheadsec.eval())
                control.par.Audiosource = source
                control.op('control_callbacks').module._set_audio_source(source)
                callbacks._synchronize_show_control()
                check(f'{mode}:{story["number"]}:{source}: routed', int(connector.op('audiosource_switch').par.index.eval())==index)
                check(f'{mode}:{story["number"]}:{source}: no clock reset', abs(float(connector.par.Playheadsec.eval())-before)<.0001)
    for enabled in (False, True):
        control.par.Loopplaylist = enabled
        configure_loop()
        check(f'loop {enabled}', str(op('/local/time').par.rangelimit.eval())==('loop' if enabled else 'hold'))
    control.par.Loopplaylist=True
    configure_loop()
    last_number = data['stories'][-1]['number']
    jump_story(last_number)
    navigate(1)
    check('next loops to first', _controller().sequencer.story_at(float(connector.par.Playheadsec.eval())*1000)['number']==1)
    navigate(-1)
    check('previous loops to last', _controller().sequencer.story_at(float(connector.par.Playheadsec.eval())*1000)['number']==last_number)
    for fade in (0,1,5,15):
        control.par.Storyfadesec=fade
        jump_story(2)
        expected=_controller().sequencer.output_opacity_at(float(connector.par.Playheadsec.eval())*1000,fade*1000)
        for index in (1,2):
            check(f'edge {index}:{fade}',abs(float(connector.op(f'story_edge_fade_{index}').par.opacity.eval())-expected)<.0001)
    check('audio files unchanged during navigation', audio_files==[str(connector.op(n).par.file.eval()) for n in ('voices_only_audio','soundscape_audio','combined_audio')])
    for node,kind in (('voices_only_audio','voices_only'),('soundscape_audio','soundscape_only'),('combined_audio','combined')):
        check(node+': current approved playlist file', Path(str(connector.op(node).par.file.eval())).resolve()==(ROOT/data['audio'][kind]).resolve())
        check(node+': no operator error', not connector.op(node).errors())
    check('third audio input', connector.op('audiosource_switch').inputs[2]==connector.op('combined_audio'))
    check('old selector disabled', not bool(control.op('story_proof_callbacks').par.active.eval()))
    check('3080 safe', str(control.par.Runtimeprofile.eval())=='3080_safe' and not bool(control.par.Livevariations.eval()))
    if saved:
        expected_project = expected_project or ('podcast.26.toe' if data['story_count']==35 else None)
        if expected_project is not None:
            check('saved project name', str(project.name)==expected_project)
        selected = getattr(connector.par, 'Playlistmanifest', None)
        check('saved playlist manifest', selected is not None and
              Path(str(selected.eval())).resolve()==(WORK/'playlist.json').resolve())
    # Restore an inviting, paused start; do not save automatically.
    control.par.Storyfadesec=1
    control.par.Crossfadesec=8
    control.par.Randomseeds=False
    control.par.Visualpath=connector.par.Visualpath='balanced'
    _controller().reload()
    jump_story(1)
    control.par.Storychoice='story1'
    control.par.Audiosource='combined'
    control.par.Audioenabled=True
    callbacks._synchronize_show_control()
    report=dict(project=str(project.name), story_count=data['story_count'],
                manifest=(WORK/'playlist.json').relative_to(ROOT).as_posix(), checks=len(checks),
                passed=sum(c['passed'] for c in checks), failed=[c for c in checks if not c['passed']],
                saved_verification=saved, model_servers_started=False, details=checks)
    (WORK/('td-reopen-audit.json' if saved else 'td-audit.json')).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('PLAYLIST_AUDIT', {k:v for k,v in report.items() if k!='details'})
    if report['failed']:
        raise RuntimeError('Playlist native audit failed')
    return report


def event_audit():
    """Exercise actual Parameter Execute events on separate application frames."""
    connector = _connector()
    control = connector.op('show_control')
    control.par.Audioenabled = False
    control.par.Play = False
    control.store('playlist_event_checks', [])
    # Commands address TD's public parameters only; no model control parameters.
    actions = [
        ("c.par.Storychoice='story5'", "q.story_at(ms)['number']==5", 'story menu'),
        ("c.par.Nextstory.pulse()", "q.story_at(ms)['number']==6", 'next pulse'),
        ("c.par.Previousstory.pulse()", "q.story_at(ms)['number']==5", 'previous pulse'),
        ("c.par.Audiosource='voices'", "int(p.op('audiosource_switch').par.index.eval())==0", 'narration event'),
        ("c.par.Audiosource='soundscape'", "int(p.op('audiosource_switch').par.index.eval())==1", 'ambient event'),
        ("c.par.Audiosource='combined'", "int(p.op('audiosource_switch').par.index.eval())==2", 'combined event'),
        ("c.par.Visualpath='original'", "q.plan['visual_path']['id']=='original'", 'original event'),
        ("c.par.Visualpath='human_figures'", "q.plan['visual_path']['id']=='human_figures'", 'human event'),
        ("c.par.Visualpath='balanced'", "q.plan['visual_path']['id']=='balanced'", 'balanced event'),
        ("c.par.Loopplaylist=False", "str(op('/local/time').par.rangelimit.eval())=='hold'", 'loop off event'),
        ("c.par.Loopplaylist=True", "str(op('/local/time').par.rangelimit.eval())=='loop'", 'loop on event'),
        ("c.par.Play=True", "bool(op('/local/time').par.play.eval())", 'play event'),
        ("c.par.Storychoice='story28'", "q.story_at(ms)['number']==28 and bool(c.par.Play.eval())", 'playing jump'),
        ("c.par.Play=False", "not bool(op('/local/time').par.play.eval())", 'pause event'),
        ("c.par.Restartplaylist.pulse()", "q.story_at(ms)['number']==1 and not bool(c.par.Play.eval())", 'restart event'),
        # Real-time clock crossings, with audio muted throughout the audit.
        ("op('/project1').time.frame=math.floor(q.stories[0]['end_ms']/1000*project.cookRate)-1; c.par.Play=True",
         "q.story_at(ms)['number']==2", 'automatic next story'),
        ("c.par.Play=False; op('/project1').time.frame=int(op('/local/time').par.rangeend.eval())-2; c.par.Play=True",
         "q.story_at(ms)['number']==1", 'full playlist wrap'),
    ]
    # Exercise the appended stories through real menu events, not helper calls.
    actions[3:3] = [(f"c.par.Storychoice='story{s['number']}'",
                    f"q.story_at(ms)['number']=={s['number']}",
                    f"appended story {s['number']} menu")
                   for s in _manifest()['stories'] if s['number'] > 35]
    control.store('playlist_event_actions', actions)
    module = "op('/project1/podcast_visualizer/show_control/playlist_callbacks').module"
    delay = 1
    for index in range(len(actions)):
        run(f'{module}.event_step({index},False)',delayFrames=delay)
        run(f'{module}.event_step({index},True)',delayFrames=delay+12)
        delay += 16
    run(f'{module}.event_finish()',delayFrames=delay)
    print('PLAYLIST_EVENTS_SCHEDULED', dict(actions=len(actions),completion_frames=delay, muted=True))


def event_step(index, verify):
    p = op('/project1/podcast_visualizer')
    c = p.op('show_control')
    q = _controller().sequencer
    ms = float(p.par.Playheadsec.eval())*1000
    command, expression, label = c.fetch('playlist_event_actions')[index]
    if verify:
        checks = c.fetch('playlist_event_checks')
        checks.append(dict(check=label,passed=bool(eval(expression)),playhead_ms=ms))
        c.store('playlist_event_checks',checks)
    else:
        exec(command)


def event_finish():
    c = op('/project1/podcast_visualizer/show_control')
    c.par.Play=False
    c.par.Audioenabled=True
    jump_story(1)
    c.par.Storychoice='story1'
    c.par.Audiosource='combined'
    c.par.Visualpath='balanced'
    checks=c.fetch('playlist_event_checks')
    report=dict(checks=len(checks),passed=sum(v['passed'] for v in checks),
                failed=[v for v in checks if not v['passed']],details=checks,model_servers_started=False)
    (WORK/'td-event-audit.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('PLAYLIST_EVENT_AUDIT',{k:v for k,v in report.items() if k!='details'})
