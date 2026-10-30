"""GestureControl Studio: native, local desktop cockpit."""
import os
import queue
import sys
import threading
import time
import traceback
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, Signal, QLockFile
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QPen, QLinearGradient, QPainterPath, QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget, QSlider, QCheckBox,
    QLineEdit, QComboBox, QScrollArea, QSizePolicy, QMessageBox)
from config import ROOT, load, save, validate
from dashboard_bridge import DashboardBridge

BG='#0a1018'
PANEL='#111b26'
MINT='#76efd1'
MUTED='#8194a8'
CONNECTIONS=[(0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),(5,9),(9,10),
             (10,11),(11,12),(9,13),(13,14),(14,15),(15,16),(13,17),(0,17),(17,18),(18,19),(19,20)]

STYLE='''
QWidget { color:#e8f0f6; font-family:"Segoe UI"; font-size:13px; }
QMainWindow, QWidget#root, QWidget#page { background:#0a1018; }
QFrame#sidebar { background:#0d1620; border-right:1px solid #1c2a38; }
QFrame#card { background:#111b26; border:1px solid #21303f; border-radius:16px; }
QFrame#metric { background:#101a24; border:1px solid #20303f; border-radius:14px; }
QLabel { background:transparent; border:0; }
QLabel#eyebrow { color:#8194a8; font-size:10px; font-weight:700; letter-spacing:2px; }
QLabel#muted { color:#8194a8; }
QLabel#heading { font-size:31px; font-weight:650; letter-spacing:-1px; }
QLabel#title { font-size:16px; font-weight:600; }
QLabel#metricValue { font-size:26px; font-weight:600; color:#dfeaf4; }
QLabel#pill { color:#76efd1; background:#15342f; border:1px solid #245448; border-radius:10px; padding:5px 10px; font-size:10px; font-weight:700; }
QPushButton { background:#1a2937; border:1px solid #2c4052; border-radius:9px; padding:10px 14px; font-weight:600; }
QPushButton:hover { background:#243b4b; border-color:#587589; }
QPushButton:pressed { background:#304e60; }
QPushButton:disabled { color:#526372; background:#13202c; border-color:#20303f; }
QPushButton#primary { background:#76efd1; color:#092720; border:0; }
QPushButton#primary:hover { background:#a0ffe5; }
QPushButton#danger { background:#34202a; color:#ff9aa8; border:1px solid #65333e; }
QPushButton#danger:hover { background:#542a37; }
QPushButton#nav { text-align:left; background:transparent; color:#91a3b4; border:0; padding:13px 15px; }
QPushButton#nav:checked { color:#8bf4d8; background:#18332f; border-left:3px solid #76efd1; }
QPushButton#nav:hover { background:#182835; color:#e8f0f6; }
QPushButton#ghost { background:transparent; border:1px solid #2a3d4c; color:#a8bbca; }
QCheckBox { spacing:10px; padding:5px 0; }
QCheckBox::indicator { width:29px; height:16px; border-radius:8px; background:#263746; border:1px solid #3b4c5d; }
QCheckBox::indicator:checked { background:#76efd1; border:1px solid #8affdc; }
QSlider::groove:horizontal { background:#263846; height:4px; border-radius:2px; }
QSlider::sub-page:horizontal { background:#76efd1; border-radius:2px; }
QSlider::handle:horizontal { background:#e5fff7; border:2px solid #76efd1; width:12px; height:12px; margin:-5px 0; border-radius:7px; }
QLineEdit, QComboBox { background:#0d1721; border:1px solid #304456; border-radius:8px; padding:10px; selection-background-color:#245b52; }
QLineEdit:focus, QComboBox:focus { border-color:#76efd1; }
QComboBox QAbstractItemView { background:#132330; selection-background-color:#255447; }
QScrollArea { border:0; background:transparent; }
QScrollBar:vertical { width:6px; background:transparent; }
QScrollBar::handle:vertical { background:#354959; border-radius:3px; min-height:30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QToolTip { background:#1c2f3d; color:#e8f0f6; border:1px solid #355569; padding:6px; }
'''

def label(text, name=None, wrap=False):
    w=QLabel(text)
    if name: w.setObjectName(name)
    w.setWordWrap(wrap)
    return w

def button(text, callback, name=None):
    w=QPushButton(text)
    w.setMinimumHeight(37)
    if name: w.setObjectName(name)
    w.setCursor(Qt.PointingHandCursor)
    w.clicked.connect(callback)
    return w

def card(name='card'):
    w=QFrame(); w.setObjectName(name)
    return w

class Workspace(QWidget):
    calibrated=Signal(list)
    def __init__(self):
        super().__init__()
        self.setMinimumSize(360,280)
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self.image=None; self.geometry_data=[]; self.showcase=False
        self.roi=[.15,.15,.85,.85]; self.calibrating=False; self.corners=[]
        self.image_rect=QRectF(); self.live=False; self.phase=0
        self.timer=QTimer(self); self.timer.timeout.connect(self.animate); self.timer.start(50)

    def animate(self):
        self.phase=(self.phase+1)%200
        if not self.live or self.showcase: self.update()

    def set_frame(self, frame, geometry):
        h,w=frame.shape[:2]
        self.image=QImage(frame.data,w,h,frame.strides[0],QImage.Format_BGR888).copy()
        self.geometry_data=geometry; self.live=True; self.update()

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        area=QRectF(self.rect()); path=QPainterPath(); path.addRoundedRect(area,12,12)
        p.setClipPath(path)
        gradient=QLinearGradient(0,0,self.width(),self.height())
        gradient.setColorAt(0,QColor('#132e37')); gradient.setColorAt(1,QColor('#0a121e'))
        p.fillRect(area,gradient)
        p.setPen(QPen(QColor('#1c3540'),1))
        for x in range(0,self.width(),32): p.drawLine(x,0,x,self.height())
        for y in range(0,self.height(),32): p.drawLine(0,y,self.width(),y)
        if self.image is not None:
            ratio=min(self.width()/self.image.width(),self.height()/self.image.height())
            iw,ih=self.image.width()*ratio,self.image.height()*ratio
            rect=QRectF((self.width()-iw)/2,(self.height()-ih)/2,iw,ih)
            self.image_rect=rect
            if not self.showcase: p.drawImage(rect,self.image)
            else:
                self.draw_region(p,rect)
                for hand in self.geometry_data:
                    pts=[QPointF(rect.x()+x*rect.width(),rect.y()+y*rect.height()) for x,y in hand['points']]
                    colour=QColor(MINT if hand['selected'] else '#3b5061')
                    if hand['selected']:
                        p.setPen(QPen(QColor(118,239,209,25),12,Qt.SolidLine,Qt.RoundCap))
                        for a,b in CONNECTIONS: p.drawLine(pts[a],pts[b])
                    p.setPen(QPen(colour,2,Qt.SolidLine,Qt.RoundCap))
                    for a,b in CONNECTIONS: p.drawLine(pts[a],pts[b])
                    p.setBrush(colour); p.setPen(Qt.NoPen)
                    for point in pts: p.drawEllipse(point,3,3)
                    if hand['selected']:
                        p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor('#e5fff7'),2))
                        p.drawEllipse(pts[8],10,10)
                        p.drawLine(pts[8]+QPointF(-16,0),pts[8]+QPointF(16,0))
                        p.drawLine(pts[8]+QPointF(0,-16),pts[8]+QPointF(0,16))
        else:
            self.image_rect=QRectF(0,0,self.width(),self.height())
            cx,cy=self.width()/2,self.height()/2-20
            p.setPen(QPen(QColor('#2b655f'),1)); p.setBrush(Qt.NoBrush)
            for radius in (52,85,118): p.drawEllipse(QPointF(cx,cy),radius,radius)
            p.setPen(QPen(QColor(MINT),3)); p.drawArc(QRectF(cx-85,cy-85,170,170),self.phase*29,750)
            p.setPen(QColor(MINT)); p.setFont(QFont('Segoe UI',30,QFont.Light))
            p.drawText(QRectF(cx-45,cy-30,90,60),Qt.AlignCenter,'G')
            p.setPen(QColor('#b8cdd6')); p.setFont(QFont('Segoe UI',12))
            p.drawText(QRectF(0,cy+135,self.width(),25),Qt.AlignCenter,'Your next move starts here.')
            p.setPen(QColor(MUTED)); p.setFont(QFont('Segoe UI',9))
            p.drawText(QRectF(0,cy+164,self.width(),22),Qt.AlignCenter,'Connect your Pixel to bring this space to life')
        if self.calibrating:
            p.fillRect(area,QColor(3,12,18,100))
            p.setPen(QColor(MINT)); p.setFont(QFont('Segoe UI',11,QFont.Bold))
            p.drawText(QRectF(12,18,self.width()-24,40),Qt.AlignCenter,
                       'Click the '+('first' if not self.corners else 'opposite')+' corner of your comfortable hand area')
            for x,y in self.corners:
                pos=QPointF(self.image_rect.x()+x*self.image_rect.width(),self.image_rect.y()+y*self.image_rect.height())
                p.drawEllipse(pos,7,7)
        if self.image is not None and not self.live:
            p.fillRect(area,QColor(3,12,18,160)); p.setPen(QColor('#ffad9c'))
            p.setFont(QFont('Segoe UI',12,QFont.Bold))
            p.drawText(area,Qt.AlignCenter,'VIDEO INTERRUPTED · Control paused')
        p.end()

    def draw_region(self,p,rect):
        a,b,c,d=self.roi
        r=QRectF(rect.x()+a*rect.width(),rect.y()+b*rect.height(),(c-a)*rect.width(),(d-b)*rect.height())
        p.setPen(QPen(QColor('#355f69'),1,Qt.DashLine)); p.setBrush(Qt.NoBrush); p.drawRect(r)
        p.setPen(QPen(QColor(MINT),2))
        for x,dx in ((r.left(),1),(r.right(),-1)):
            for y,dy in ((r.top(),1),(r.bottom(),-1)):
                p.drawLine(QPointF(x,y),QPointF(x+16*dx,y)); p.drawLine(QPointF(x,y),QPointF(x,y+16*dy))

    def mousePressEvent(self,event):
        if not self.calibrating or not self.image_rect.contains(event.position()): return
        r=self.image_rect
        self.corners.append(((event.position().x()-r.x())/r.width(),(event.position().y()-r.y())/r.height()))
        if len(self.corners)==2:
            a,b=self.corners
            roi=[min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1])]
            if roi[2]-roi[0]>=.15 and roi[3]-roi[1]>=.15:
                self.calibrating=False; self.roi=roi; self.calibrated.emit(roi)
            self.corners=[]
        self.update()

class Studio(QMainWindow):
    def __init__(self, autoconnect=True, demo=False):
        super().__init__()
        if not getattr(Studio,'fonts_loaded',False):
            for filename in ('segoeui.ttf','seguisb.ttf','segoeuil.ttf','seguisym.ttf'):
                QFontDatabase.addApplicationFont(os.path.join(os.environ.get('WINDIR','C:\\Windows'),'Fonts',filename))
            Studio.fonts_loaded=True
        self.config=load(); self.bridge=None; self.worker=None; self.last_sequence=-1
        self.events=queue.SimpleQueue(); self.pending_settings={}; self.closing=False
        self.demo=demo; self.last_state={}; self.last_ui_update=0
        self.setWindowTitle('GestureControl Studio')
        mark=QPixmap(64,64); mark.fill(Qt.transparent)
        painter=QPainter(mark); painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen); painter.setBrush(QColor('#102b2b')); painter.drawRoundedRect(0,0,64,64,16,16)
        painter.setPen(QPen(QColor(MINT),3)); painter.setBrush(Qt.NoBrush); painter.drawEllipse(QPointF(32,32),23,23)
        painter.setFont(QFont('Segoe UI',24,QFont.DemiBold)); painter.drawText(mark.rect(),Qt.AlignCenter,'G'); painter.end()
        self.setWindowIcon(QIcon(mark))
        self.resize(1380,900); self.setMinimumSize(1120,780)
        root=QWidget(); root.setObjectName('root'); self.setCentralWidget(root)
        outer=QHBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        main=QVBoxLayout(); main.setContentsMargins(20,16,20,12); main.setSpacing(14); outer.addLayout(main,1)
        head=QHBoxLayout()
        brand=label('GestureControl','title'); brand.setStyleSheet('font-size:23px;font-weight:650;color:#b9f6e5;')
        head.addWidget(brand); head.addStretch()
        self.nav=[]
        for i,name in enumerate(('Controls','Camera settings','Help')):
            b=button(name,lambda checked=False,n=i:self.navigate(n),'nav'); b.setCheckable(True)
            self.nav.append(b); head.addWidget(b)
        self.showcase_btn=button('◇  Showcase view',self.toggle_showcase,'ghost'); head.addWidget(self.showcase_btn)
        main.addLayout(head)
        self.pages=QStackedWidget(); main.addWidget(self.pages,1)
        self.build_control(); self.build_connection(); self.build_guide()
        footer=QHBoxLayout()
        self.compact_status=label('Offline','muted'); footer.addWidget(self.compact_status)
        footer.addStretch()
        self.notice=label('','muted'); footer.addWidget(self.notice)
        footer.addSpacing(16); footer.addWidget(label('F8  STOP','eyebrow')); main.addLayout(footer)
        self.nav[0].setChecked(True)
        self.settings_timer=QTimer(self); self.settings_timer.setSingleShot(True)
        self.settings_timer.timeout.connect(self.flush_settings)
        self.timer=QTimer(self); self.timer.timeout.connect(self.tick); self.timer.start(33)
        self.setStyleSheet(STYLE)
        if autoconnect and not demo: QTimer.singleShot(250,self.connect_camera)

    def build_control(self):
        page=QWidget(); page.setObjectName('page'); layout=QVBoxLayout(page)
        layout.setContentsMargins(0,0,0,0); layout.setSpacing(14)
        split=QHBoxLayout(); split.setSpacing(18)
        preview=card(); pv=QVBoxLayout(preview); pv.setContentsMargins(16,16,16,14); pv.setSpacing(13)
        top=QHBoxLayout(); top.addWidget(label('LIVE WORKSPACE','eyebrow')); top.addStretch()
        self.live_pill=label('OFFLINE','pill'); top.addWidget(self.live_pill); pv.addLayout(top)
        self.workspace=Workspace(); self.workspace.roi=self.config['roi']; self.workspace.calibrated.connect(self.finish_calibration)
        pv.addWidget(self.workspace,1)
        under=QHBoxLayout(); self.feed_info=label('Pixel 5  /  640 × 480','muted'); under.addWidget(self.feed_info)
        under.addStretch(); under.addWidget(label('●  Active hand     ●  Other hand','muted')); pv.addLayout(under)
        buttons=QHBoxLayout(); self.connect_btn=button('Connect camera',self.connection_toggle,'ghost')
        buttons.addWidget(self.connect_btn)
        self.calibrate_btn=button('Calibrate area',self.calibrate,'ghost'); buttons.addWidget(self.calibrate_btn)
        self.switch_btn=button('Switch hand',self.switch_hand,'ghost'); buttons.addWidget(self.switch_btn)
        buttons.addWidget(button('Full frame',self.full_frame,'ghost'))
        pv.addLayout(buttons); split.addWidget(preview,1)
        controls=card(); controls.setFixedWidth(306)
        ctl=QVBoxLayout(controls); ctl.setContentsMargins(21,20,21,19); ctl.setSpacing(12)
        ctl.addWidget(label('COMMAND CENTRE','eyebrow'))
        self.state_title=label('Standby','heading'); self.state_title.setStyleSheet('font-size:25px; font-weight:600;')
        ctl.addWidget(self.state_title)
        self.state_detail=label('Your camera will appear here. Mouse control stays off until you enable it.','muted',True)
        self.state_detail.setMinimumHeight(44); ctl.addWidget(self.state_detail)
        self.control_btn=button('Enable control  →',self.toggle_control,'primary'); self.control_btn.setMinimumHeight(44); ctl.addWidget(self.control_btn)
        self.stop_btn=button('■   Stop control     F8',self.stop_control,'danger'); ctl.addWidget(self.stop_btn)
        scroll=QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        settings=QWidget(); settings.setObjectName('settings')
        settings.setStyleSheet('QWidget#settings { background:#111b26; }')
        scroll.setWidget(settings); ctl.addWidget(scroll,1)
        ctl=QVBoxLayout(settings); ctl.setContentsMargins(0,5,7,0); ctl.setSpacing(8)
        ctl.addWidget(label('MOVEMENT','eyebrow'))
        self.toggles={}
        for key,text in [('absolute_cursor','Direct finger-to-screen mapping'),('relaxed_pose','Relaxed hand pose'),('auto_resume','Resume when hand returns'),('cursor_only','Cursor only · no clicks')]:
            toggle=QCheckBox(text); toggle.setChecked(self.config[key]); self.toggles[key]=toggle
            toggle.toggled.connect(lambda value,k=key:self.queue_setting(k,value)); ctl.addWidget(toggle)
        smooth_head=QHBoxLayout(); smooth_head.addWidget(label('Smoothing','muted')); smooth_head.addStretch()
        self.smooth_value=label('Direct' if not self.config['smoothing'] else f"{int(self.config['smoothing']*1000)} ms")
        smooth_head.addWidget(self.smooth_value); ctl.addLayout(smooth_head)
        self.smoothing=QSlider(Qt.Horizontal); self.smoothing.setRange(0,250); self.smoothing.setValue(int(self.config['smoothing']*1000))
        self.smoothing.valueChanged.connect(self.smoothing_changed); ctl.addWidget(self.smoothing)
        ctl.addWidget(label('Direct ←                       → Steadier','muted'))
        gain_head=QHBoxLayout(); gain_head.addWidget(label('Relative sensitivity','muted')); gain_head.addStretch()
        self.gain_value=label(f"{self.config['sensitivity']:.1f}×"); gain_head.addWidget(self.gain_value); ctl.addLayout(gain_head)
        self.gain=QSlider(Qt.Horizontal); self.gain.setRange(2,50); self.gain.setValue(round(self.config['sensitivity']*10))
        self.gain.setEnabled(not self.config['absolute_cursor']); self.gain.valueChanged.connect(self.gain_changed); ctl.addWidget(self.gain)
        ctl.addWidget(label('Direct mode uses your calibrated area.','muted',True))
        ctl.addSpacing(8); ctl.addWidget(label('GESTURE TUNING','eyebrow'))
        for title,key,low,high,scale,suffix in [
            ('Gesture hold','dwell',100,1000,1000,'ms'),
            ('Click cooldown','click_cooldown',250,3000,1000,'ms'),
            ('Scroll sensitivity','scroll_speed',1,100,1,'')]:
            heading=QHBoxLayout(); heading.addWidget(label(title,'muted')); heading.addStretch()
            value=round(self.config[key]*scale)
            output=label(f'{value} {suffix}'.strip()); heading.addWidget(output); ctl.addLayout(heading)
            slider=QSlider(Qt.Horizontal); slider.setRange(low,high); slider.setValue(value)
            def changed(v,k=key,s=scale,unit=suffix,out=output):
                out.setText(f'{v} {unit}'.strip()); self.queue_setting(k,v/s)
            slider.valueChanged.connect(changed); ctl.addWidget(slider)
        ctl.addStretch()
        split.addWidget(controls); layout.addLayout(split,1)
        self.pages.addWidget(page)

    def build_connection(self):
        page=QWidget(); page.setObjectName('page'); base=QVBoxLayout(page); base.setContentsMargins(0,0,0,0)
        box=card(); form=QVBoxLayout(box); form.setContentsMargins(28,26,28,26); form.setSpacing(16)
        form.addWidget(label('THE CONNECTION','eyebrow')); form.addWidget(label('One phone. A new kind of mouse.','heading'))
        form.addWidget(label('Use a local DroidCam stream over Wi-Fi, or its Windows camera index over USB.','muted',True))
        form.addSpacing(12); form.addWidget(label('Camera index or local stream URL','title'))
        self.source=QLineEdit(self.config['source']); self.source.setPlaceholderText('http://192.168.x.x:4747/video/force/640x480'); form.addWidget(self.source)
        fields=QHBoxLayout()
        for title,key,values in [('Capture backend','backend',['DSHOW','MSMF','AUTO']),('Rotation','rotation',['0','90','180','270'])]:
            col=QVBoxLayout(); col.addWidget(label(title,'muted')); combo=QComboBox(); combo.addItems(values); combo.setCurrentText(str(self.config[key]))
            setattr(self,key+'_combo',combo); col.addWidget(combo); fields.addLayout(col)
        form.addLayout(fields)
        self.mirror=QCheckBox('Mirror camera · natural hand movement'); self.mirror.setChecked(self.config['mirror']); form.addWidget(self.mirror)
        buttons=QHBoxLayout(); buttons.addWidget(button('Save && reconnect',self.reconnect,'primary'))
        self.scan_btn=button('Scan USB cameras',self.scan,'ghost'); buttons.addWidget(self.scan_btn); buttons.addStretch(); form.addLayout(buttons)
        self.scan_result=label('Direct Wi-Fi is configured for watermark-free standard definition.','muted',True); form.addWidget(self.scan_result)
        form.addStretch(); info=card('metric'); inf=QVBoxLayout(info); inf.setContentsMargins(20,18,20,18)
        inf.addWidget(label('A GOOD SIGNAL MAKES A GREAT EXPERIENCE','eyebrow'))
        inf.addWidget(label('Keep DroidCam open on the Pixel and zoom at 1×. Use even lighting and show your full controlling hand. For USB, connect through the DroidCam Windows client first.','muted',True)); form.addWidget(info)
        base.addWidget(box); self.pages.addWidget(page)

    def build_guide(self):
        page=QWidget(); page.setObjectName('page'); base=QVBoxLayout(page); base.setContentsMargins(0,0,0,0)
        box=card(); layout=QVBoxLayout(box); layout.setContentsMargins(28,25,28,25); layout.setSpacing(18)
        layout.addWidget(label('MAKE IT SECOND NATURE','eyebrow')); layout.addWidget(label('A little movement goes a long way.','heading'))
        rows=[('01','Connect & enable','Camera preview starts without mouse control. Click Enable control when you are ready.'),
              ('02','Move naturally','In relaxed cursor mode, open or fold your other fingers. Your index fingertip maps to the screen.'),
              ('03','Choose your hand','The green hand controls the cursor. The grey hand is ignored. Switch hand changes the selection.'),
              ('04','Make room','Calibrate area lets you click opposite corners of a comfortable working region. Centre maps to screen centre.'),
              ('05','Show it off','Showcase view replaces the camera picture with a live hand skeleton on a clean grid. Nothing is uploaded.'),
              ('F8','Stop, instantly','The emergency stop stays off until you deliberately enable control again. F9 also enables or pauses.')]
        for number,title,description in rows:
            row=QHBoxLayout(); n=label(number,'metricValue'); n.setFixedWidth(55); n.setStyleSheet('font-size:24px;color:#76efd1;')
            row.addWidget(n); text=QVBoxLayout(); text.setSpacing(3); text.addWidget(label(title,'title')); text.addWidget(label(description,'muted',True)); row.addLayout(text,1); layout.addLayout(row)
        layout.addStretch(); layout.addWidget(button('Open full setup & gesture guide',lambda:os.startfile(str(ROOT/'README.md')),'ghost'))
        base.addWidget(box); self.pages.addWidget(page)

    def navigate(self,index):
        self.pages.setCurrentIndex(index)
        for i,b in enumerate(self.nav): b.setChecked(i==index)

    def toggle_showcase(self):
        self.workspace.showcase=not self.workspace.showcase
        self.showcase_btn.setText('◈  Camera view' if self.workspace.showcase else '◇  Showcase view')
        self.workspace.update(); self.navigate(0)

    def connect_camera(self):
        if self.worker and self.worker.is_alive(): return
        self.flush_settings(); self.bridge=DashboardBridge(); bridge=self.bridge
        self.last_sequence=-1; self.workspace.image=None; self.workspace.live=False
        self.workspace.geometry_data=[]; self.workspace.update(); self.last_state={}
        self.notice.setText('Connecting…'); self.connect_btn.setText('Disconnect')
        def work():
            try:
                from runtime import run
                run(self.config.copy(),bridge=bridge)
            except Exception as exc:
                (ROOT/'last_error.log').write_text(traceback.format_exc())
                bridge.publish(state={'enabled':False,'status':'Connection error','error':str(exc)})
            finally: bridge.finished.set()
        self.worker=threading.Thread(target=work,daemon=True,name='GestureControl-tracking'); self.worker.start()

    def disconnect_camera(self):
        if self.bridge:
            self.bridge.pause(); self.bridge.send('quit')
        self.notice.setText('Disconnecting camera…')

    def connection_toggle(self):
        if self.worker and self.worker.is_alive(): self.disconnect_camera()
        else: self.connect_camera()

    def toggle_control(self):
        if not self.bridge or self.bridge.finished.is_set():
            self.notice.setText('Connect camera first'); return
        if self.last_state.get('enabled') or self.last_state.get('auto_resume') or self.last_state.get('arm_pending'):
            self.stop_control()
        else:
            self.bridge.send('resume'); self.notice.setText('Show your controlling hand')

    def stop_control(self):
        if self.bridge: self.bridge.pause()
        self.notice.setText('Control paused'); self.workspace.calibrating=False

    def switch_hand(self):
        if self.bridge and not self.bridge.finished.is_set():
            self.bridge.send('switch'); self.notice.setText('Hand switched')

    def calibrate(self):
        if not self.workspace.live:
            self.notice.setText('Connect camera first'); return
        was_calibrating=self.workspace.calibrating
        self.stop_control(); self.workspace.calibrating=not was_calibrating
        self.workspace.corners=[]; self.workspace.update()
        self.notice.setText('Calibration cancelled' if was_calibrating else 'Click two opposite corners')

    def finish_calibration(self,roi):
        self.queue_setting('roi',roi); self.flush_settings()
        self.notice.setText('Area saved · enable control to continue')

    def full_frame(self):
        self.stop_control()
        self.queue_setting('roi',[0.0,0.0,1.0,1.0]); self.flush_settings()
        self.notice.setText('Full frame · enable control to continue')

    def queue_setting(self,key,value):
        self.pending_settings[key]=value
        if key=='absolute_cursor': self.gain.setEnabled(not value)
        if key=='cursor_only' and not value:
            self.stop_control()
            self.notice.setText('Gestures selected · enable control to continue')
        self.settings_timer.start(250)

    def smoothing_changed(self,value):
        self.smooth_value.setText(f'{value} ms' if value else 'Direct'); self.queue_setting('smoothing',value/1000)

    def gain_changed(self,value):
        self.gain_value.setText(f'{value/10:.1f}×'); self.queue_setting('sensitivity',value/10)

    def flush_settings(self):
        if not self.pending_settings: return
        changes=self.pending_settings.copy(); self.pending_settings.clear()
        try:
            self.config=validate(self.config|changes)
            if self.bridge and not self.bridge.finished.is_set(): self.bridge.send('settings',changes)
            else: save(self.config)
            self.workspace.roi=self.config['roi']
        except (ValueError,OSError) as exc: self.notice.setText(str(exc))

    def reconnect(self):
        try:
            self.config=validate(self.config|dict(source=self.source.text(),backend=self.backend_combo.currentText(),
                                                rotation=int(self.rotation_combo.currentText()),mirror=self.mirror.isChecked()))
        except ValueError as exc:
            self.scan_result.setText(str(exc)); return
        self.disconnect_camera()
        def wait():
            if self.worker and self.worker.is_alive(): QTimer.singleShot(100,wait); return
            save(self.config); self.connect_camera(); self.navigate(0)
        QTimer.singleShot(100,wait)

    def scan(self):
        if self.worker and self.worker.is_alive():
            self.scan_result.setText('Disconnect the camera on the Control room page before scanning.'); return
        self.scan_btn.setEnabled(False); self.scan_result.setText('Scanning camera indices 0–5. This can take up to 45 seconds.')
        backend=self.backend_combo.currentText()
        def work():
            from camera import probe
            result=[f'{i}: {probe(str(i),backend)}' for i in range(6)]
            self.events.put(('scan','\n'.join(result)))
        threading.Thread(target=work,daemon=True).start()

    def tick(self):
        while not self.events.empty():
            kind,value=self.events.get_nowait()
            if kind=='scan': self.scan_result.setText(value); self.scan_btn.setEnabled(True)
        if not self.bridge: return
        seq,frame,state,updated,geometry=self.bridge.snapshot()
        self.last_state=state
        alive=bool(self.worker and self.worker.is_alive())
        if seq!=self.last_sequence and frame is not None:
            self.workspace.set_frame(frame,geometry); self.last_sequence=seq
        fresh=alive and time.monotonic()-updated<1 and state.get('frame_age',10)<.5
        self.workspace.live=fresh; self.workspace.update()
        enabled=state.get('enabled',False) and fresh
        requested=state.get('auto_resume',False) or state.get('arm_pending',False)
        self.live_pill.setText('● LIVE' if fresh else 'CONNECTING' if alive and frame is None else 'OFFLINE')
        self.connect_btn.setText('Disconnect' if alive else 'Connect camera')
        self.control_btn.setEnabled(alive); self.calibrate_btn.setEnabled(fresh); self.switch_btn.setEnabled(fresh)
        self.control_btn.setText('Pause control' if enabled or requested else 'Enable control  →')
        self.state_title.setText('In control.' if enabled else 'Finding your hand.' if requested and fresh else 'Ready when you are.' if fresh else 'Connecting…' if alive else 'Standby')
        detail=state.get('error') or state.get('status','Waiting for camera')
        if fresh and not requested and not enabled: detail='Preview is live. Enable control to move the cursor with your hand.'
        elif enabled: detail='Your fingertip is the cursor. The other hand stays out of the equation.'
        elif requested and fresh: detail=state.get('arm_blocker') or 'Acquiring your selected hand…'
        self.state_detail.setText(detail)
        rate=f"{state.get('fps',0):.0f} fps" if fresh else 'Offline'
        hand=(state.get('selected_hand')+' hand') if state.get('selected_hand') else 'Auto hand'
        mode='Cursor only' if state.get('cursor_only',True) else 'Full gestures'
        self.compact_status.setText(f'{rate}   ·   {hand}   ·   {mode}')
        if fresh and self.notice.text()=='Connecting…': self.notice.clear()
        if 'width' in state: self.feed_info.setText(f"Pixel 5  /  {state['width']} × {state['height']}  /  {'Skeleton' if self.workspace.showcase else 'Camera'}")
        if state.get('config'): self.workspace.roi=state['config']['roi']
        if self.closing and not alive: self.close()

    def closeEvent(self,event):
        if self.worker and self.worker.is_alive():
            self.closing=True; self.disconnect_camera(); event.ignore()
            QTimer.singleShot(2500,self.force_close)
        else:
            self.flush_settings(); event.accept()

    def force_close(self):
        if not self.closing: return
        if self.bridge:
            self.bridge.pause()
            if self.bridge.camera:
                self.bridge.camera.close()
        # Worker is a daemon; input is disabled even if native inference is stalled.
        QApplication.instance().quit()

def main(autoconnect=True):
    app=QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName('GestureControl Studio')
    app.setStyle('Fusion')
    instance_lock=QLockFile(str(ROOT/'studio.lock'))
    if not instance_lock.tryLock(0):
        QMessageBox.information(None,'GestureControl Studio','Studio is already open. Switch to its existing window.')
        return 0
    window=Studio(autoconnect=autoconnect)
    screen=app.primaryScreen().availableGeometry()
    window.resize(min(1380,screen.width()-40),min(900,screen.height()-50))
    window.move(screen.center()-window.rect().center())
    window.show()
    return app.exec()

if __name__=='__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main())
