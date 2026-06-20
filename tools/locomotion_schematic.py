# -*- coding: utf-8 -*-
"""Full visual schematic set for the Mark 1 Locomotion deck.
Generates 4 A3-landscape sheets (SVG) -> vector PDF, faithful to the netlist.
"""
import subprocess, os
from pypdf import PdfWriter, PdfReader

SCALE=4; W=420*SCALE; H=297*SCALE                       # A3 landscape, 4 units/mm
FONT="Arial, Helvetica, sans-serif"
NAVY="#1f3050"; TEAL="#20b2a6"; INK="#27313f"; SUB="#5b6472"; LINE="#c5cfdc"; BAND="#eef3f9"
GREEN="#179b86"; GREEN_F="#e8f6f2"                       # clean domain
RED="#c0493a";   RED_F="#fbeeec"                         # motor domain
AMBER="#b9831e"; AMBER_F="#fdf4e3"                       # servo domain
GRAY="#6b7484";  GRAY_F="#eef1f5"                        # isolation
I2C="#2563b0"; PWRC="#c0493a"; CTRL="#5b6472"; USBC="#7a3fb0"; ISOC="#b9831e"

DIAG="/Users/alphaworkz/Desktop/Friday Labs Os/docs/build/diagrams"
BUILD="/Users/alphaworkz/Desktop/Friday Labs Os/docs/build"
os.makedirs(DIAG,exist_ok=True)

def esc(t): return str(t).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
def R(x,y,w,h,fill="#ffffff",stroke=INK,sw=2.4,rx=10):
    return [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>']
def Rd(x,y,w,h,stroke=GRAY,sw=2,rx=12,dash="9 7",fill="none"):
    return [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" stroke-dasharray="{dash}"/>']
def T(x,y,s,size=15,col=INK,anchor="start",weight="normal"):
    return [f'<text x="{x}" y="{y}" font-size="{size}" fill="{col}" text-anchor="{anchor}" font-weight="{weight}" font-family="{FONT}">{esc(s)}</text>']
def L(pts,col=CTRL,sw=2.2,dash=None):
    d=f' stroke-dasharray="{dash}"' if dash else ""
    p=" ".join(f"{x},{y}" for x,y in pts)
    return [f'<polyline points="{p}" fill="none" stroke="{col}" stroke-width="{sw}"{d} stroke-linejoin="round" stroke-linecap="round"/>']
def DOT(x,y,col=CTRL,r=4.5): return [f'<circle cx="{x}" cy="{y}" r="{r}" fill="{col}"/>']

def block(x,y,w,h,title,sub=None,fill="#ffffff",stroke=INK,tcol=NAVY):
    o=[R(x,y,w,h,fill,stroke)]
    if sub:
        o.append(T(x+w/2,y+27,title,17,tcol,"middle","bold"))
        o.append(T(x+w/2,y+47,sub,12,SUB,"middle"))
    else:
        o.append(T(x+w/2,y+h/2+6,title,17,tcol,"middle","bold"))
    return o

def rail(x,y,name,col=PWRC,anchor="start"):
    # power-rail flag: short bar + bold name
    o=[f'<rect x="{x-3}" y="{y-9}" width="6" height="18" rx="2" fill="{col}"/>']
    if anchor=="start": o.append(T(x+11,y+5,name,13,col,"start","bold"))
    else: o.append(T(x-11,y+5,name,13,col,"end","bold"))
    return o

def gnd(x,y,label=None,col=INK):
    o=[L([(x,y),(x,y+11)],col,2.2),
       f'<line x1="{x-13}" y1="{y+11}" x2="{x+13}" y2="{y+11}" stroke="{col}" stroke-width="2.4"/>',
       f'<line x1="{x-8}" y1="{y+16}" x2="{x+8}" y2="{y+16}" stroke="{col}" stroke-width="2.4"/>',
       f'<line x1="{x-3.5}" y1="{y+21}" x2="{x+3.5}" y2="{y+21}" stroke="{col}" stroke-width="2.4"/>']
    if label: o.append(T(x,y+36,label,11,col,"middle","bold"))
    return o

def offsheet(x,y,text,col,side="L"):
    """off-sheet connector tag (pentagon)."""
    h=22; w=10+7*len(text)
    if side=="L":   # points left
        pts=f"{x},{y} {x-w+14},{y} {x-w+14},{y-h/2} {x-12},{y-h/2} {x-12},{y+h/2} {x-w+14},{y+h/2} {x-w+14},{y}"
        # simpler: rounded tag with notch on right
    # Use a simple rounded tag instead for robustness
    if side=="L":
        o=[f'<path d="M{x} {y} L{x-14} {y-12} L{x-w} {y-12} L{x-w} {y+12} L{x-14} {y+12} Z" fill="#ffffff" stroke="{col}" stroke-width="2"/>',
           T(x-16,y+5,text,12.5,col,"end","bold")]
    else:
        o=[f'<path d="M{x} {y} L{x+14} {y-12} L{x+w} {y-12} L{x+w} {y+12} L{x+14} {y+12} Z" fill="#ffffff" stroke="{col}" stroke-width="2"/>',
           T(x+16,y+5,text,12.5,col,"start","bold")]
    return o

def motor(cx,cy,label,r=30):
    return [f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#ffffff" stroke="{RED}" stroke-width="2.6"/>',
            T(cx,cy+5,"M",18,RED,"middle","bold"),
            T(cx,cy+r+16,label,11.5,INK,"middle","bold")]

def legend(items, x=60, y=H-66):
    o=[T(x,y,"LEGEND",12,SUB,"start","bold")]
    cx=x+78
    for lab,col in items:
        o.append(f'<line x1="{cx}" y1="{y-4}" x2="{cx+34}" y2="{y-4}" stroke="{col}" stroke-width="3.5"/>')
        o.append(T(cx+42,y,lab,12,SUB,"start"))
        cx+=42+12+8*len(lab)+24
    return o

def frame():
    return [f'<rect x="22" y="22" width="{W-44}" height="{H-44}" fill="none" stroke="{NAVY}" stroke-width="2.5" rx="4"/>']

def topstrip(title,sub):
    return ['<rect x="22" y="22" width="%d" height="58" fill="%s" rx="4"/>'%(W-44,NAVY),
            '<rect x="22" y="74" width="%d" height="6" fill="%s"/>'%(W-44,TEAL),
            T(46,58,"FRIDAY LABS  -  MARK 1",16,"#9fb0c8","start","bold"),
            T(W-46,50,title,21,"#ffffff","end","bold"),
            T(W-46,71,sub,12.5,"#aebbcf","end")]

def titleblock(no,total,title):
    bw,bh=470,92; bx,by=W-bw-30,H-bh-30
    o=[R(bx,by,bw,bh,"#ffffff",NAVY,2,6),
       f'<line x1="{bx}" y1="{by+34}" x2="{bx+bw}" y2="{by+34}" stroke="{NAVY}" stroke-width="1.2"/>',
       f'<line x1="{bx+bw-150}" y1="{by}" x2="{bx+bw-150}" y2="{by+bh}" stroke="{NAVY}" stroke-width="1.2"/>',
       T(bx+14,by+23,"Mark 1 - Locomotion Control Unit",14,NAVY,"start","bold"),
       T(bx+14,by+54,title,15,INK,"start","bold"),
       T(bx+14,by+76,"Friday Labs Inc. - Design stage - schematic per netlist Draft 1.0",10.5,SUB,"start"),
       T(bx+bw-75,by+23,"FULL SCHEMATIC",10.5,TEAL,"middle","bold"),
       T(bx+bw-75,by+57,f"SHEET {no}/{total}",17,NAVY,"middle","bold"),
       T(bx+bw-75,by+78,"Rev A - 2026",10.5,SUB,"middle")]
    return o

def flatten(x):
    if isinstance(x,str): return [x]
    out=[]
    for i in x: out.extend(flatten(i))
    return out

def svgdoc(parts):
    body="\n".join(flatten(parts))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="420mm" height="297mm" '
            f'viewBox="0 0 {W} {H}">\n'
            f'<rect width="{W}" height="{H}" fill="#ffffff"/>\n{body}\n</svg>\n')

# ----------------------------------------------------------------------------
def sheet1():
    P=frame()+topstrip("Power, Isolation Domains & E-Stop","Sheet 1 - distribution, galvanic split, fail-open safety")
    # domain bands
    P+=[ '<rect x="40" y="100" width="640" height="760" fill="%s" opacity="0.45" rx="14"/>'%GREEN_F,
         T(60,124,"CLEAN DOMAIN  (logic / sensors)",13,GREEN,"start","bold"),
         '<rect x="700" y="100" width="600" height="540" fill="%s" opacity="0.5" rx="14"/>'%RED_F,
         T(720,124,"MOTOR DOMAIN  (isolated)",13,RED,"start","bold"),
         '<rect x="700" y="660" width="600" height="200" fill="%s" opacity="0.55" rx="14"/>'%AMBER_F,
         T(720,684,"SERVO DOMAIN  (isolated)",13,AMBER,"start","bold"),
         Rd(688,96,2,768,GRAY,2.4,0,"10 8") ]
    P+=[T(694,92,"GALVANIC ISOLATION",11,GRAY,"middle","bold")]
    # input + estop contactor (straddles the barrier)
    P+=block(70,150,250,96,"BACKBONE INPUT","M12 - +14V8_RAW (fused) + GND",fill="#ffffff",stroke=NAVY)
    P+=block(380,150,280,110,"E-STOP CONTACTOR","NC loop coil-enable - FAILS OPEN",fill="#ffffff",stroke=RED,tcol=RED)
    P+=L([(320,198),(380,198)],PWRC,3); P+=rail(326,182,"+14V8_RAW",PWRC)
    P+=L([(660,205),(720,205)],PWRC,3); P+=rail(666,189,"+14V8_SW",PWRC)
    # buck off RAW (always-on)
    P+=L([(195,246),(195,300)],PWRC,3); P+=DOT(195,246,PWRC)
    P+=block(70,300,250,98,"5V / 3A BUCK","+14V8_RAW -> +5V_CLEAN",fill="#ffffff",stroke=GREEN,tcol=GREEN)
    P+=block(70,440,250,90,"+3V3_CLEAN","via ESP32 onboard LDO (Sheet 2)",fill="#ffffff",stroke=GREEN,tcol=GREEN)
    P+=L([(195,398),(195,440)],PWRC,2.6)
    P+=rail(340,349,"+5V_CLEAN  -> ESP32 (Sheet 2)",GREEN); P+=L([(320,349),(335,349)],GREEN,2.6)
    P+=rail(340,485,"+3V3_CLEAN -> sensors/isolators",GREEN); P+=L([(320,485),(335,485)],GREEN,2.6)
    # e-stop opto sense (power -> clean)
    P+=block(380,300,280,118,"E-STOP SENSE OPTO","LED across +14V8_SW (series R)","#ffffff",GRAY,GRAY)
    P+=[T(520,372,"phototransistor -> ESTOP_LIVE",12,INK,"middle"),
        T(520,392,"(power -> clean, dedicated opto)",11,SUB,"middle")]
    P+=offsheet(380,400,"ESTOP_LIVE -> ESP32 GPIO39 (Sheet 2)",GRAY,"L")
    # motor-domain converters
    P+=block(720,150,250,100,"ISOLATED 5V DC-DC","+14V8_SW -> +5V_ISO","#ffffff",RED,RED)
    P+=[T(845,236,"motor-side logic ref",11,SUB,"middle")]
    P+=block(1010,150,270,100,"INA219 + SHUNT","motor-bus current sense (Sheet 4)","#ffffff",RED,RED)
    P+=L([(970,200),(1010,200)],PWRC,2.4,"6 5")
    # servo-domain converters
    P+=block(720,700,250,100,"6V UBEC","+14V8_SW -> +6V_SRV (servo power)","#ffffff",AMBER,AMBER)
    P+=block(1010,700,270,100,"+5V_SRV LDO","from +6V_SRV (servo logic ref)","#ffffff",AMBER,AMBER)
    P+=L([(970,750),(1010,750)],"#b9831e",2.6)
    # +14V8_SW distribution bus down the barrier into motor + servo
    P+=L([(690,205),(845,205),(845,150)],PWRC,3)   # to iso5
    P+=L([(845,205),(845,150)],PWRC,0.1)
    P+=L([(690,560),(845,560),(845,700)],PWRC,3); P+=DOT(690,205,PWRC)
    P+=[T(700,548,"+14V8_SW -> servo + pawl",11,PWRC,"start","bold")]
    # rails board
    rx,ry=1330,150
    P+=[R(rx,ry,250,330,"#ffffff",NAVY,2,8), T(rx+125,ry+26,"POWER RAILS",14,NAVY,"middle","bold"),
        f'<line x1="{rx}" y1="{ry+38}" x2="{rx+250}" y2="{ry+38}" stroke="{LINE}" stroke-width="1"/>']
    rails=[("+14V8_RAW","always-on",PWRC),("+14V8_SW","E-stop cut",PWRC),("+5V_CLEAN","clean",GREEN),
           ("+3V3_CLEAN","clean",GREEN),("+5V_ISO","motor",RED),("+6V_SRV","servo",AMBER),("+5V_SRV","servo",AMBER)]
    yy=ry+62
    for nm,dsc,c in rails:
        P+=[f'<rect x="{rx+14}" y="{yy-11}" width="6" height="16" rx="2" fill="{c}"/>',
            T(rx+30,yy+3,nm,12.5,c,"start","bold"), T(rx+236,yy+3,dsc,11,SUB,"end")]
        yy+=38
    # star ground
    sx,sy=820,920
    P+=gnd(sx,sy-2,None,INK)
    P+=[T(sx,sy+52,"STAR GROUND  (single point at battery negative)",13,NAVY,"middle","bold")]
    for gx,lab,c in [(300,"GND_CLEAN",GREEN),(820,"GND_MOTOR",RED),(1340,"GND_SRV",AMBER)]:
        P+=L([(gx,880),(gx,sy-2),(sx,sy-2)],c,2.6)
        P+=[f'<rect x="{gx-3}" y="{868}" width="6" height="14" fill="{c}"/>',T(gx,856,lab,12,c,"middle","bold")]
    P+=DOT(sx,sy-2,INK,6)
    P+=legend([("power",PWRC),("clean rail",GREEN),("motor",RED),("servo",AMBER),("isolation",GRAY)])
    P+=titleblock(1,4,"Power, Isolation & E-Stop")
    return svgdoc(P)

# ----------------------------------------------------------------------------
def sheet2():
    P=frame()+topstrip("Controller, I2C Sensors & Isolation Bank","Sheet 2 - ESP32-S3 pinout, encoder mux tree, current-sense isolation")
    # ---- isolation-bank reference table (top-left) ----
    tx,ty,tw=60,150,330
    P+=R(tx,ty,tw,300,"#ffffff",NAVY,2,8)
    P+=T(tx+tw/2,ty+26,"ISOLATION BANK (ISO7741 x5)",13,NAVY,"middle","bold")
    P+=[f'<line x1="{tx}" y1="{ty+38}" x2="{tx+tw}" y2="{ty+38}" stroke="{LINE}" stroke-width="1"/>']
    rows=[("#1","DRV_PWM1..4 -> MDD10A PWM"),("#2","DRV_PWM5-6, DIR1-2"),("#3","DRV_DIR3..6"),
          ("#4","SRV_PWM1..4 -> servos"),("#5","PAWL_REL -> FET (+3 spare)")]
    yy=ty+64
    for a,b in rows:
        P+=T(tx+16,yy+3,a,12.5,TEAL,"start","bold"); P+=T(tx+54,yy+3,b,11,INK,"start")
        P+=[f'<line x1="{tx}" y1="{yy+18}" x2="{tx+tw}" y2="{yy+18}" stroke="{BAND}" stroke-width="1"/>']
        yy+=46
    P+=T(tx,ty+328,"All ISO7741 channels run clean -> power (4/0 part).",10.5,SUB,"start")
    P+=T(tx,ty+348,"E-stop sense is a separate opto (Sheet 1).",10.5,SUB,"start")
    # ---- ESP32 block ----
    ex,ey,ew,eh=460,150,250,600
    P+=R(ex,ey,ew,eh,"#ffffff",GREEN,2.8,12)
    P+=T(ex+ew/2,ey+30,"ESP32-S3",20,GREEN,"middle","bold")
    P+=T(ex+ew/2,ey+50,"motion controller (clean domain)",11.5,SUB,"middle")
    P+=[f'<line x1="{ex}" y1="{ey+62}" x2="{ex+ew}" y2="{ey+62}" stroke="{LINE}" stroke-width="1"/>']
    # left pins -> drivers/estop, tiny sheet-ref tags in the gap (no collision w/ table)
    left=[("GPIO4-7","DRV_PWM1..4","Sh3",CTRL),("GPIO15,16","DRV_PWM5..6","Sh3",CTRL),
          ("GPIO17,18","DRV_DIR1..2","Sh3",CTRL),("GPIO8-11","DRV_DIR3..6","Sh3",CTRL),
          ("GPIO12-14,21","SRV_PWM1..4","Sh4",AMBER),("GPIO38","PAWL_REL","Sh4",RED),
          ("GPIO39","ESTOP_LIVE in","Sh1",GRAY)]
    yy=ey+92
    for gp,net,sh,c in left:
        P+=T(ex+12,yy-3,gp,10.5,SUB,"start","bold"); P+=T(ex+12,yy+13,net,12,INK,"start","bold")
        P+=L([(ex,yy+4),(ex-24,yy+4)],c,2.2)
        P+=[f'<path d="M{ex-24} {yy+4} l8 -5 l0 10 Z" fill="{c}"/>']
        P+=T(ex-36,yy+8,sh,10.5,c,"end","bold")
        yy+=68
    # right pins
    def rpin(yv,gp,net,c):
        out=T(ex+ew-12,yv-3,gp,10.5,SUB,"end","bold")+T(ex+ew-12,yv+13,net,12.5,c,"end","bold")
        out+=L([(ex+ew,yv+4),(ex+ew+24,yv+4)],c,2.4)
        return out
    yI2C0=ey+110; yLED=ey+250; yUSB=ey+350; yI2C1=ey+540
    P+=rpin(yI2C0,"GPIO1/2 I2C0","SDA0/SCL0",I2C)
    P+=rpin(yLED,"GPIO48","STAT_LED",INK)
    P+=rpin(yUSB,"GPIO19/20","USB DM/DP",USBC)
    P+=rpin(yI2C1,"GPIO41/42 I2C1","SDA1/SCL1",I2C)
    P+=T(ex+ew/2,ey+eh-40,"5V <- +5V_CLEAN  -  3V3 -> +3V3_CLEAN",10,GREEN,"middle","bold")
    P+=T(ex+ew/2,ey+eh-22,"GND -> GND_CLEAN (clean star leg)",10,SUB,"middle")
    lx=ex+ew+24
    # STAT_LED inline (right of pin, clear of the IMU)
    P+=L([(lx,yLED+4),(744,yLED+4)],CTRL,2.2)
    P+=[f'<circle cx="754" cy="{yLED+4}" r="10" fill="#ffffff" stroke="{TEAL}" stroke-width="2.4"/>']
    P+=T(754,yLED+26,"+330R",9.5,SUB,"middle"); P+=gnd(754,yLED+30,None,INK)
    # USB-C inline block (below the IMU)
    P+=L([(lx,yUSB+4),(726,yUSB+4)],USBC,2.2)
    P+=block(726,yUSB-22,176,52,"USB-C -> Core Hub","CDC link","#ffffff",USBC,USBC)
    # ---- I2C0: mux + BNO085 + 6 encoders (clean vertical comb) ----
    P+=T(786,142,"I2C0 (clean) - mux, IMU + 6 wheel encoders - pull-ups 4.7k -> +3V3_CLEAN",11.5,GREEN,"start","bold")
    jx=760; mux_x,mux_y=800,236
    P+=L([(lx,yI2C0+4),(jx,yI2C0+4)],I2C,2.6); P+=DOT(jx,yI2C0+4,I2C)
    P+=L([(jx,yI2C0+4),(jx,422)],I2C,2.6)
    P+=block(mux_x,mux_y,170,84,"TCA9548A","I2C mux - 0x70","#ffffff",GREEN,GREEN)
    P+=L([(jx,mux_y+42),(mux_x,mux_y+42)],I2C,2.6)
    P+=block(mux_x,380,170,84,"BNO085","IMU - 0x4A","#ffffff",GREEN,GREEN)
    P+=L([(jx,422),(mux_x,422)],I2C,2.6)
    enc_x=1300; trunk=1230
    P+=L([(mux_x+170,mux_y+42),(trunk,mux_y+42)],GREEN,2.4)
    P+=L([(trunk,204),(trunk,634)],GREEN,2.4)
    for i in range(6):
        ry=204+i*86
        P+=block(enc_x,ry-30,150,62,f"AS5600 #{i+1}",f"encoder 0x36 - ch{i}","#ffffff",GREEN,GREEN)
        P+=L([(trunk,ry),(enc_x,ry)],GREEN,2.2); P+=DOT(trunk,ry,GREEN,3.5)
        P+=T((trunk+enc_x)/2,ry-6,f"SD{i}/SC{i}",10,GREEN,"middle","bold")
    P+=T(786,700,"each AS5600 reads a magnet on its wheel shaft (one per drive wheel)",10.5,SUB,"start")
    # ---- I2C1 isolated -> INA219 ----
    P+=T(786,775,"I2C1 (clean -> motor, galvanically isolated)",11.5,RED,"start","bold")
    P+=L([(lx,yI2C1+4),(734,yI2C1+4),(734,838),(800,838)],I2C,2.6)
    P+=block(800,790,210,96,"ISO1640","isolated I2C buffer","#ffffff",GRAY,GRAY)
    P+=T(905,906,"VCC1 3V3 / VCC2 +5V_ISO - pull-ups both sides",10,SUB,"middle")
    P+=block(1110,790,210,96,"INA219","bus current - 0x40","#ffffff",RED,RED)
    P+=L([(1010,838),(1110,838)],I2C,2.6); P+=T(1060,826,"SDA2/SCL2",10,I2C,"middle","bold")
    P+=offsheet(1320,838,"shunt in +14V8_SW (Sheet 4)",RED,"R")
    P+=legend([("I2C",I2C),("control",CTRL),("USB",USBC)])
    P+=titleblock(2,4,"Controller, Sensors & Isolation")
    return svgdoc(P)

# ----------------------------------------------------------------------------
def sheet3():
    P=frame()+topstrip("Drive Subsystem - 6 Channels (fully expanded)","Sheet 3 - ESP32 -> ISO7741 x3 -> MDD10A x3 -> 6 drive motors")
    P+=[f'<rect x="660" y="100" width="960" height="890" fill="{RED_F}" opacity="0.4" rx="14"/>']
    P+=T(680,124,"MOTOR DOMAIN (isolated)",13,RED,"start","bold")
    P+=Rd(648,96,2,896,GRAY,2.2,0,"10 8"); P+=T(652,92,"ISOLATION",10.5,GRAY,"middle","bold")
    P+=T(610,150,"inputs <- ESP32 (Sheet 2)",10.5,SUB,"end")
    # ISO7741 isolators
    iso=[("ISO7741 #1",["DRV_PWM1","DRV_PWM2","DRV_PWM3","DRV_PWM4"],["M1_P","M2_P","M3_P","M4_P"],150),
         ("ISO7741 #2",["DRV_PWM5","DRV_PWM6","DRV_DIR1","DRV_DIR2"],["M5_P","M6_P","M1_D","M2_D"],470),
         ("ISO7741 #3",["DRV_DIR3","DRV_DIR4","DRV_DIR5","DRV_DIR6"],["M3_D","M4_D","M5_D","M6_D"],790)]
    for title,ins,outs,iy in iso:
        P+=[R(700,iy,180,190,"#ffffff",GRAY,2.4,10),T(790,iy+26,title,15,NAVY,"middle","bold"),
            T(790,iy+44,"clean -> motor",11,SUB,"middle")]
        for k,(ni,no) in enumerate(zip(ins,outs)):
            ry=iy+72+k*30
            P+=L([(648,ry),(700,ry)],CTRL,2.2)
            P+=T(644,ry-4,ni,10.5,CTRL,"end","bold")
            P+=L([(880,ry),(916,ry)],RED,2.2)
            P+=T(920,ry+4,no,10.5,RED,"start","bold")
    # MDD10A drivers x3 (each dual -> 2 motors)
    mdd=[("MDD10A-A",[("M1",1),("M2",2)],150),("MDD10A-B",[("M3",3),("M4",4)],470),("MDD10A-C",[("M5",5),("M6",6)],790)]
    for title,chans,my in mdd:
        P+=[R(1040,my,210,200,"#ffffff",RED,2.6,10),T(1145,my+26,title,16,RED,"middle","bold"),
            T(1145,my+44,"dual 10A - B+ +14V8_SW",10,SUB,"middle"),
            T(1145,my+60,"logic ref +5V_ISO - GND_MOTOR",9.5,SUB,"middle")]
        for k,(mlab,mn) in enumerate(chans):
            chy=my+96+k*78
            P+=T(1052,chy-6,f"{mlab}: PWM<-{mlab}_P  DIR<-{mlab}_D",10.5,INK,"start","bold")
            P+=T(1052,chy+12,"PWM 10k pull-down -> GND_MOTOR",9,SUB,"start")
            P+=L([(1250,chy),(1336,chy)],RED,2.8)
            cx,cy=1360,chy
            P+=[f'<circle cx="{cx}" cy="{cy}" r="23" fill="#ffffff" stroke="{RED}" stroke-width="2.6"/>']
            P+=T(cx,cy+6,"M",16,RED,"middle","bold")
            P+=T(cx+30,cy-2,f"drive {mn}",11,INK,"start","bold")
            P+=T(cx+30,cy+14,"37D ~70:1",9.5,SUB,"start")
            P+=T(cx,cy-30,"100nF",9,SUB,"middle")
        P+=T(1145,my+218,"1000uF bulk + 100nF across each B+/B-",9,SUB,"middle")
    # power feed bus
    P+=[f'<rect x="980" y="180" width="6" height="810" fill="{PWRC}" opacity="0.5"/>']
    P+=T(986,124,"+14V8_SW (E-stop cut) -> shunt/INA219 (Sheet 4)",11,PWRC,"start","bold")
    for my in (180,500,820):
        P+=L([(983,my),(1040,my)],PWRC,2.4); P+=DOT(983,my,PWRC)
    # fail-safe note
    P+=[R(60,470,540,300,BAND,NAVY,1.6,8),T(80,500,"FAIL-SAFE ON SIGNAL LOSS",14,NAVY,"start","bold")]
    P+=T(80,536,"- Dead isolator / lost PWM -> motor-side 10k pull-down",11.5,INK,"start")
    P+=T(92,556,"-> PWM low -> motor OFF.",11.5,INK,"start")
    P+=T(80,586,"- E-stop opens +14V8_SW -> MDD10A B+ removed",11.5,INK,"start")
    P+=T(92,606,"-> all 6 drive motors dead.",11.5,INK,"start")
    P+=T(80,636,"- Pull-downs live on the isolated (power) side: hold the",11.5,INK,"start")
    P+=T(92,656,"safe state even if clean domain / isolators are unpowered.",11.5,INK,"start")
    P+=T(80,686,"- 37D-class gearmotor; AS5600 shaft encoder feedback",11.5,INK,"start")
    P+=T(92,706,"on I2C0 mux (Sheet 2).",11.5,INK,"start")
    P+=T(80,742,"Drive map: A=M1,M2  -  B=M3,M4  -  C=M5,M6",11,SUB,"start","bold")
    P+=legend([("control",CTRL),("motor signal",RED),("power",PWRC)])
    P+=titleblock(3,4,"Drive Subsystem x6")
    return svgdoc(P)

# ----------------------------------------------------------------------------
def sheet4():
    P=frame()+topstrip("Steering, Parking Pawls & Current Sense","Sheet 4 - 4 steer servos, power-to-release pawls, motor-bus INA219")
    # servo domain
    P+=[f'<rect x="640" y="100" width="960" height="360" fill="{AMBER_F}" opacity="0.5" rx="14"/>',
        T(660,124,"SERVO DOMAIN  (isolated)  -  +6V_SRV / +5V_SRV / GND_SRV",12.5,AMBER,"start","bold")]
    P+=block(700,170,200,150,"ISO7741 #4","clean -> servo","#ffffff",GRAY,GRAY)
    P+=offsheet(560,245,"SRV_PWM1..4 (Sheet 2)",AMBER,"L"); P+=L([(560,245),(700,245)],AMBER,2.4)
    for j in range(4):
        sy=160+j*72; col=AMBER
        P+=L([(900,200+j*30),(1000-0,200+j*30)],AMBER,2.2)
    # 4 servos
    for j in range(4):
        sx=1010; sy=150+j*74
        P+=block(sx,sy,300,60,f"STEER SERVO {j+1}","DS3218 - signal SRV"+str(j+1)+" - V+ +6V_SRV - GND_SRV","#ffffff",AMBER,AMBER)
        P+=L([(900,180+j*4+ j*0+ 0+ (200+j*30-180-j*4) ),(900,200+j*30)],AMBER,0.1)
        P+=L([(900,200+j*30),(1010,sy+30)],AMBER,2.2)
    # pawl domain
    P+=[f'<rect x="640" y="490" width="960" height="370" fill="{RED_F}" opacity="0.45" rx="14"/>',
        T(660,514,"PARKING PAWLS  (motor domain)  -  power-to-release",12.5,RED,"start","bold")]
    P+=block(700,560,200,140,"ISO7741 #5","clean -> motor (+3 spare ch)","#ffffff",GRAY,GRAY)
    P+=offsheet(560,630,"PAWL_REL (Sheet 2)",RED,"L"); P+=L([(560,630),(700,630)],RED,2.4)
    # MOSFET
    P+=L([(900,630),(990,630)],RED,2.4); P+=T(945,620,"100R",10,SUB,"middle")
    mx,my=1000,600
    P+=[R(mx,my,140,90,"#ffffff",RED,2.4,8),T(mx+70,my+34,"N-MOSFET",14,RED,"middle","bold"),
        T(mx+70,my+54,"low-side",11,SUB,"middle"),T(mx+70,my+72,"gate 10k -> GND_MOTOR",9.5,SUB,"middle")]
    P+=L([(990,630),(990,710),(1070,710)],RED,2.2); P+=T(945,690,"10k pull-down",9.5,SUB,"middle")
    P+=gnd(1070,712,None,INK)
    # solenoids x4 paralleled
    P+=[f'<rect x="1200" y="540" width="6" height="280" fill="{PWRC}" opacity="0.6"/>',T(1212,556,"+14V8_SW",11,PWRC,"start","bold")]
    P+=L([(1140,645),(1175,645),(1175,760)],RED,2.4)   # mosfet drain -> low side bus
    P+=T(1100,640,"drain",10,SUB,"middle")
    for s in range(4):
        cyl=1300+s*70; ytop=600
        P+=[f'<rect x="{cyl}" y="{ytop}" width="44" height="84" rx="6" fill="#ffffff" stroke="{RED}" stroke-width="2.2"/>',
            T(cyl+22,ytop+34,"PAWL",10,RED,"middle","bold"),T(cyl+22,ytop+50,f"sol {s+1}",10,SUB,"middle")]
        # high side to +14V8_SW, low side to bus
        P+=L([(cyl+22,ytop),(cyl+22,560),(1203,560)],PWRC,2)
        P+=L([(cyl+22,ytop+84),(cyl+22,760),(1175,760)],RED,2)
        # flyback diode
        P+=[f'<path d="M{cyl-14} {ytop+30} l0 24 l12 -12 Z" fill="none" stroke="{SUB}" stroke-width="1.8"/>',
            f'<line x1="{cyl-2}" y1="{ytop+30}" x2="{cyl-2}" y2="{ytop+54}" stroke="{SUB}" stroke-width="1.8"/>']
    P+=DOT(1175,760,RED); P+=DOT(1203,560,PWRC)
    P+=T(1300,720,"4 solenoids paralleled - flyback diode across each coil",11,SUB,"start")
    # current sense block
    P+=[R(60,150,520,250,"#ffffff",RED,2,8),T(320,178,"MOTOR-BUS CURRENT SENSE",14,RED,"middle","bold"),
        f'<line x1="60" y1="190" x2="580" y2="190" stroke="{LINE}" stroke-width="1"/>']
    P+=[T(80,222,"Shunt in series with the +14V8_SW motor feed;",11.5,INK,"start"),
        T(80,244,"INA219 (0x40) reads it, VS = +5V_ISO.",11.5,INK,"start"),
        T(80,266,"I2C reaches the clean domain only through ISO1640",11.5,INK,"start"),
        T(80,288,"(Sheet 2) - the sense path is galvanically isolated.",11.5,INK,"start")]
    # shunt drawing
    P+=L([(120,340),(190,340)],PWRC,3); P+=[f'<rect x="190" y="330" width="60" height="20" fill="none" stroke="{RED}" stroke-width="2.2"/>',T(220,326,"SHUNT",9.5,SUB,"middle")]
    P+=L([(250,340),(330,340)],PWRC,3); P+=T(150,330,"+14V8_SW",10,PWRC,"middle","bold"); P+=T(300,330,"-> MDD10A",10,PWRC,"middle")
    P+=block(360,310,200,70,"INA219","0x40 - VS +5V_ISO","#ffffff",RED,RED)
    P+=L([(220,350),(220,375),(360,375)],I2C,2.2,"5 4")
    # fail-safe note
    P+=[R(60,470,520,150,BAND,NAVY,1.6,8),T(72,496,"FAIL-SAFE SUMMARY",13,NAVY,"start","bold"),
        T(72,522,"- Lost PAWL_REL / dead ISO#5 -> gate 10k pull-down -> solenoids",11,INK,"start"),
        T(72,542,"  de-energize -> PAWLS ENGAGE (power-to-release).",11,INK,"start"),
        T(72,566,"- E-stop removes +14V8_SW -> servos unpowered + pawls engage.",11,INK,"start"),
        T(72,590,"- ISO7741 #5 has 3 spare channels for future actuators.",11,INK,"start")]
    P+=legend([("servo signal",AMBER),("motor",RED),("power",PWRC),("I2C",I2C)])
    P+=titleblock(4,4,"Steering, Pawls & Current Sense")
    return svgdoc(P)

# ----------------------------------------------------------------------------
sheets=[("locomotion-full-schematic-1",sheet1()),("locomotion-full-schematic-2",sheet2()),
        ("locomotion-full-schematic-3",sheet3()),("locomotion-full-schematic-4",sheet4())]
pdfs=[]
for name,svg in sheets:
    sp=os.path.join(DIAG,name+".svg"); open(sp,"w").write(svg)
    pp="/tmp/"+name+".pdf"; subprocess.run(["rsvg-convert","-f","pdf","-o",pp,sp],check=True)
    subprocess.run(["rsvg-convert","-w","1700","-o","/tmp/"+name+".png",sp],check=True)
    pdfs.append(pp)
w=PdfWriter()
for p in pdfs: w.append(PdfReader(p))
outpdf=os.path.join(BUILD,"Locomotion Deck - Full Schematic.pdf")
with open(outpdf,"wb") as f: w.write(f)
print("PAGES:",len(PdfReader(outpdf).pages)); print("PDF ->",outpdf)
print("SVGs ->",DIAG)
