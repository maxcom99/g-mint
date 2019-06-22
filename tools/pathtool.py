from abstractparameters import *
from gcode import *
from PyQt5 import QtGui

import datetime
import geometry
import traceback

class PathTool(ItemWithParameters):
    def __init__(self,  path=None,  model=None, viewUpdater=None, tool=None, source=None,  **kwargs):
        ItemWithParameters.__init__(self,  **kwargs)
        if path is None:
            filename= QtGui.QFileDialog.getOpenFileName(None, 'Open file', '',  "GCode files (*.ngc)")
            self.path = read_gcode(filename[0])
        else:
            self.path=path
        self.viewUpdater=viewUpdater
        self.outpaths=[self.path]
        self.model=model
        self.source = source
        self.tool = tool
        feedrate=1000
        if self.tool is not None:
            feedrate =self.tool.feedrate.getValue()
        startdepth=0
        enddepth=0
        outputFile = "gcode/output.ngc"
        if model !=None:
            startdepth=model.maxv[2]
            enddepth=model.minv[2]
            if model.filename is not None:
                outputFile = model.filename.split(".stl")[0] + ".ngc"
        else:
            #print self.path.path
            if self.path.getPathLength()>0:
                startdepth=max([p.position[2] for p in self.path.get_draw_path() if p.position is not None])
                enddepth=min([p.position[2] for p in self.path.get_draw_path() if p.position is not None])
        self.startDepth=NumericalParameter(parent=self,  name='start depth',  value=startdepth,  enforceRange=False,  step=1)
        self.stopDepth=NumericalParameter(parent=self,  name='end depth ',  value=enddepth,   enforceRange=0,   step=1)
        self.maxDepthStep=NumericalParameter(parent=self,  name='max. depth step',  value=10.0,  min=0.1,  max=100,  step=1)
        self.rampdown=NumericalParameter(parent=self,  name='rampdown per mm (0=off)',  value=0.1,  min=0.0,  max=10,  step=0.01)
        self.traverseHeight=NumericalParameter(parent=self,  name='traverse height',  value=startdepth+5.0,  enforceRange=False,  step=1.0)
        self.laser_mode = NumericalParameter(parent=self,  name='laser mode',  value=0.0,  min=0.0,  max=1.0,  enforceRange=True,  step=1.0)
        self.depthStepping=ActionParameter(parent=self,  name='Apply depth stepping',  callback=self.applyDepthStep)
        self.removeNonCutting=ActionParameter(parent=self,  name='Remove non-cutting points',  callback=self.removeNoncuttingPoints)
        self.clean=ActionParameter(parent=self,  name='clean paths',  callback=self.cleanColinear)
        self.precision = NumericalParameter(parent=self,  name='precision',  value=0.005,  min=0.001,  max=1,  step=0.001)
        self.trochoidalDiameter=NumericalParameter(parent=self,  name='tr. diameter',  value=3.0,  min=0.0,  max=100,  step=0.1)
        self.trochoidalStepover=NumericalParameter(parent=self,  name='tr. stepover',  value=1.0,  min=0.1,  max=5,  step=0.1)
        self.trochoidalOrder=NumericalParameter(parent=self,  name='troch. order',  value=0.0,  min=0,  max=100000,  step=1)
        self.trochoidalSkip=NumericalParameter(parent=self,  name='skip',  value=1.0,  min=1,  max=100000,  step=1)
        self.trochoidalOuterDist=NumericalParameter(parent=self,  name='outer dist',  value=1.0,  min=0,  max=100000,  step=1)
        self.trochoidalMilling = ActionParameter(parent=self,  name='trochoidal',  callback=self.calcTrochoidalMilling)
        self.feedrate=NumericalParameter(parent=self,  name='default feedrate',  value=feedrate,  min=1,  max=5000,  step=10,  callback=self.updateEstimate)
        self.plunge_feedrate = NumericalParameter(parent=self, name='plunge feedrate', value=feedrate/2.0, min=1, max=5000,
                                           step=10, callback=self.updateEstimate)
        self.filename=TextParameter(parent=self,  name="output filename",  value=outputFile)
        self.saveButton=ActionParameter(parent=self,  name='Save to file',  callback=self.save)
        self.appendButton=ActionParameter(parent=self,  name='append from file',  callback=self.appendFromFile)
        self.estimatedTime=TextParameter(parent=self,  name='est. time',  editable=False)
        self.estimatedDistance=TextParameter(parent=self,  name='distance',  editable=False)

        self.parameters=[self.startDepth, 
                                    self.stopDepth,    
                                    self.maxDepthStep,  
                                    self.rampdown,  
                                    self.traverseHeight,   
                                    self.laser_mode, 
                                    [self.depthStepping,   
                                    self.removeNonCutting],  
                                    [self.clean, self.precision], 
                                    
                                    [self.trochoidalDiameter,  self.trochoidalStepover], 
                                    [self.trochoidalOrder, self.trochoidalSkip],
                                    self.trochoidalOuterDist ,
                                    self.trochoidalMilling, 
                                    self.feedrate, self.plunge_feedrate,
                                    self.filename,  
                                    self.saveButton, 
                                    self.appendButton, 
                                    self.estimatedTime,  
                                    self.estimatedDistance]
        self.updateView()
    
    def updatePath(self,  path):
        self.path = path
        self.outpaths=[self.path]
        self.updateView()

    
    def cleanColinear(self):
        
        if len(self.outpaths)==0:
            self.path.outpaths=GCode()
            self.path.outpaths.combinePath(self.path.path)
        inpath=self.outpaths
        precision = self.precision.getValue()
        for path in inpath:
            i=1
            while i<len(path.path)-1:
                if not path.path[i].rapid and norm(normalize(array(path.path[i].position)-array(path.path[i-1].position))-normalize(array(path.path[i+1].position)-array(path.path[i].position)))<precision:
                    del path.path[i]
                i+=1
        if self.viewUpdater!=None:
            self.viewUpdater(self.path)

    def getCompletePath(self):
        completePath = GCode(path=[])
        completePath.default_feedrate=self.feedrate.getValue()
        completePath.laser_mode = (self.laser_mode.getValue() > 0.5)
        print("gCP lasermode", completePath.laser_mode, self.laser_mode.getValue())
        for path in self.outpaths:
            completePath.combinePath(path)
        return completePath

    def updateView(self):
        for line in traceback.format_stack():
            print(line.strip())
        if self.viewUpdater!=None:
            print("pt:", self.tool)
            self.viewUpdater(self.getCompletePath(), tool=self.tool)
        self.updateEstimate()
        
    def updateEstimate(self,  val=None):
        self.path.default_feedrate = self.feedrate.getValue()
        estimate = None

        estimate = self.getCompletePath().estimate()
        self.estimatedTime.updateValue("%s (%s)"%(str(datetime.timedelta(seconds=int(estimate[1]*60))),
                                                           str(datetime.timedelta(seconds=int(estimate[5]*60)))))
        self.estimatedDistance.updateValue("{:.1f} (c {:.0f})".format(estimate[0],  estimate[3],  estimate[4]))


    def appendFromFile(self):
        filename= QtGui.QFileDialog.getOpenFileName(None, 'Open file', '',  "GCode files (*.ngc)")
        new_path =read_gcode(filename)
        self.path.appendPath(new_path)
        self.outpaths = [self.path]
        self.updateView()
        
    def save(self):
        completePath=self.getCompletePath()
        completePath.default_feedrate=self.feedrate.getValue()
        completePath.laser_mode = (self.laser_mode.getValue()>0.5)

        completePath.write(self.filename.getValue())
        self.updateEstimate()


    def segmentPath(self, path):
        buffered_points = []  # points that need to be finished after rampdown
        # split into segments of closed loops, or separated by rapids
        segments = []
        for p in path:
            # buffer points to detect closed loops (for ramp-down)
            if p.position is not None:
                if p.rapid: #flush at rapids
                    if len(buffered_points)>0:
                        segments.append(buffered_points)
                        buffered_points = []
                buffered_points.append(p)
                # detect closed loops,
                if (len(buffered_points) > 2 and dist2D(buffered_points[0].position, p.position) < 0.00001):
                    segments.append(buffered_points)
                    buffered_points = []
        if len(buffered_points)>0:
            segments.append(buffered_points)
            buffered_points = []
        return segments

    def applyRampDown(self, segment, previousCutDepth, currentDepthLimit, rampdown):
        lastPoint=None
        output = []


        #check if this is a closed segment:
        if dist2D(segment[0].position, segment[-1].position)<0.0001:
            # ramp "backwards" to reach target depth at start of segment
            ramp = []
            sl =  len(segment)
            pos = sl - 1
            currentDepth = min([p.position[2] for p in segment]) #get deepest point in segment
            while currentDepth < previousCutDepth:
                p = segment[pos]
                nd = max(p.position[2], currentDepthLimit)
                is_in_contact = True
                dist = dist2D(segment[pos].position, segment[(pos+1)%sl].position)
                currentDepth += dist * rampdown # spiral up

                if (nd<currentDepth):
                    nd = currentDepth
                    is_in_contact=False
                ramp.append(GPoint(position=(p.position[0], p.position[1], nd), rapid=p.rapid,
                                     inside_model=p.inside_model, in_contact=is_in_contact))

                pos = (pos-1+sl) % sl

            p=ramp[-1]
            output.append(GPoint(position=(p.position[0], p.position[1], self.traverseHeight.getValue()), rapid=True,
                                  inside_model=p.inside_model, in_contact=False))
            for p in reversed(ramp):
                output.append(p)
            for p in segment[1:]:
                output.append(p)
            p=segment[-1]
            output.append(GPoint(position=(p.position[0], p.position[1], self.traverseHeight.getValue()), rapid=True,
                                  inside_model=p.inside_model, in_contact=False))

        else: # for open segments, apply forward ramping
            lastPoint = None
            for p in segment:
                nd = max(p.position[2], currentDepthLimit)
                is_in_contact = True

                # check if rampdown is active, and we're below previously cut levels, then limit plunge rate accordingly
                if not p.rapid and rampdown != 0 and nd < previousCutDepth and lastPoint != None:
                    dist = dist2D(p.position, lastPoint.position)
                    lastPointDepth = min(lastPoint.position[2], previousCutDepth)
                    if (lastPointDepth - nd) > dist * rampdown:  # plunging to deeply - need to reduce depth for this point
                        nd = lastPointDepth - dist * rampdown;
                        is_in_contact = False
                        # buffer this point to finish closed path at currentDepthLimit

                output.append(GPoint(position=(p.position[0], p.position[1], nd), rapid=p.rapid,
                                      inside_model=p.inside_model, in_contact=is_in_contact))
                lastPoint = output[-1]

        return output

    def applyStepping(self, segment, currentDepthLimit, finished):
        output = []
        for p in segment:
            # is_in_contact=p.in_contact
            is_in_contact = True
            nd = p.position[2]
            if nd < currentDepthLimit:
                nd = currentDepthLimit
                is_in_contact = False;
                finished = False

            output.append(GPoint(position=(p.position[0], p.position[1], nd), rapid=p.rapid,
                                  inside_model=p.inside_model, in_contact=is_in_contact))
        return output, finished

    def applyDepthStep(self):
        print("apply depth stepping")
        self.outpaths=[]
        finished=False
        depthStep=self.maxDepthStep.getValue()
        currentDepthLimit=self.startDepth.getValue()-depthStep
        endDepth=self.stopDepth.getValue()
        
        if currentDepthLimit<endDepth:
            currentDepthLimit=endDepth
        previousCutDepth=self.startDepth.getValue()
        rampdown=self.rampdown.getValue()
        lastPoint=None

        # split into segments of closed loops, or separated by rapids
        segments = self.segmentPath(self.path.path)

        while not finished:
            finished=True
            newpath=[]

            for s in segments:
                segment_output, finished = self.applyStepping(s, currentDepthLimit, finished)

                if (rampdown!=0) and len(segment_output)>3:
                    segment_output = self.applyRampDown(segment_output, previousCutDepth, currentDepthLimit, rampdown)
                for p in segment_output:
                    newpath.append(p)

            if currentDepthLimit<=endDepth:
                finished=True

            previousCutDepth=currentDepthLimit
            currentDepthLimit-=depthStep
            if currentDepthLimit<endDepth:
                currentDepthLimit=endDepth
            self.outpaths.append(GCode(newpath))
        self.updateView()
        
    def removeNoncuttingPoints(self):
        new_paths=[]
        skipping=False
        for path_index,  path in enumerate(self.outpaths):
            if path_index==0:
                new_paths.append(path)
            else:
                newpath=[]
                for p_index,  p in enumerate(path):
                    # check if previous layer already got in contact with final surface
                    if  self.path.outpaths[path_index-1][p_index].in_contact:
                        if not skipping:
                            # skip point at safe traverse depth
                            newpath.append(GPoint(position=(p.position[0],  p.position[1], self.traverseHeight.getValue()),  rapid=True,  inside_model=p.inside_model,  in_contact=False))
                            skipping=True
                    else:
                        if skipping:
                            newpath.append(GPoint(position=(p.position[0],  p.position[1], self.traverseHeight.getValue()),  rapid=True,  inside_model=p.inside_model,  in_contact=p.in_contact))
                            skipping=False
                        #append point to new output
                        newpath.append(GPoint(position=(p.position[0],  p.position[1],  p.position[2]),  rapid=p.rapid,  inside_model=p.inside_model,  in_contact=p.in_contact))
                new_paths.append(GCode(newpath))
        
        self.outpaths=new_paths
        self.updateView()
            
    def calcTrochoidalMilling(self):
        new_paths=[]
        lastPoint = None
        radius = self.trochoidalDiameter.getValue()/2.0
        distPerRev = self.trochoidalStepover.getValue()
        rampdown=self.rampdown.getValue()
        steps_per_rev = 20
        stock_poly = None
        if self.source is not None:
            stock_poly = self.source.getStockPolygon()
        #for path_index,  path in enumerate(self.path.path):
            
        newpath=[]
        angle = 0
        for p_index,  p in enumerate(self.path.path):
            # when plunging, check if we already cut this part before
            cutting = True
            plunging = False
            for cp in self.path.path[0:p_index]:
                if lastPoint is not None and lastPoint.position[2]>p.position[2] and geometry.dist(p.position, cp.position) <min(radius, cp.dist_from_model):
                    cutting = False

            if p.rapid or p.order>self.trochoidalOrder.getValue()  or p.dist_from_model< self.trochoidalOuterDist.getValue() or not cutting :
                newpath.append(GPoint(position = (p.position),  rapid = p.rapid,  inside_model=p.inside_model,  in_contact=p.in_contact))
            else:
                if p.order%self.trochoidalSkip.getValue()==0: #skip paths
                    if lastPoint is not None:
                        if lastPoint.position[2] > p.position[2]:
                            plunging = True
                        else:
                            plunging = False
                        dist=sqrt((p.position[0]-lastPoint.position[0])**2 + (p.position[1]-lastPoint.position[1])**2 + (p.position[2]-lastPoint.position[2])**2)
                        distPerRev = self.trochoidalStepover.getValue()
                        if plunging:
                            dradius = radius
                            if  p.dist_from_model is not None:
                                dradius = min(min(radius, p.dist_from_model), self.tool.diameter.getValue()/2.0)
                            if rampdown>0.0:
                                distPerRev = rampdown*(dradius*2.0*pi)

                        steps =  int(float(steps_per_rev)*dist/distPerRev)+1
                        dradius = 0.0
                        for i in range(0,  steps):
                            angle -= (dist/float(distPerRev) / float(steps)) * 2.0*PI
                            dradius = radius
                            bore_expansion = False
                            if  p.dist_from_model is not None and lastPoint.dist_from_model is not None:
                                dradius = min(radius, lastPoint.dist_from_model*(1.0-(float(i)/steps)) + p.dist_from_model*(float(i)/steps))
                            if  p.dist_from_model is not None and lastPoint.dist_from_model is None:
                                dradius = min(radius, p.dist_from_model)
                            # if plunging and radius is larger than tool diameter, bore at smaller radius and expand out
                            if plunging:
                                if dradius>self.tool.diameter.getValue():
                                    dradius = self.tool.diameter.getValue()/2.0
                                    bore_expansion = True

                            x = lastPoint.position[0]*(1.0-(float(i)/steps)) + p.position[0]*(float(i)/steps) + dradius * sin(angle)
                            y = lastPoint.position[1]*(1.0-(float(i)/steps)) + p.position[1]*(float(i)/steps) + dradius * cos(angle)
                            z = lastPoint.position[2]*(1.0-(float(i)/steps)) + p.position[2]*(float(i)/steps)

                            cutting = True
                            if stock_poly is not None and not stock_poly.pointInside((x, y, z)):
                                cutting = False
                            for cp in self.path.path[0:p_index]:
                                if cp.dist_from_model is not None and geometry.dist((x, y, z), cp.position) < min(radius, cp.dist_from_model) - 0.5*self.trochoidalStepover.getValue():
                                    cutting = False
                            if cutting:
                                feedrate=None
                                if plunging:
                                    feedrate=self.plunge_feedrate.getValue()
                                newpath.append(GPoint(position=(x, y, z), rapid=p.rapid, inside_model=p.inside_model,in_contact=p.in_contact, feedrate = feedrate))

                        if bore_expansion:
                            distPerRev = self.trochoidalStepover.getValue()
                            dist = min(radius, p.dist_from_model) - dradius + distPerRev
                            steps = int(float(steps_per_rev) * (dist / distPerRev) )
                            for i in range(0, steps):
                                angle -= (dist / float(distPerRev) / float(steps)) * 2.0 * PI
                                dradius += dist/steps
                                if dradius>p.dist_from_model:
                                    dradius=p.dist_from_model
                                x = p.position[0] + dradius * sin(angle)
                                y = p.position[1] + dradius * cos(angle)
                                z = p.position[2]
                                cutting = True
                                if stock_poly is not None and not stock_poly.pointInside((x, y, z)):
                                    cutting = False
                                if cutting:
                                    newpath.append(GPoint(position = (x,  y,  z),  rapid = p.rapid,  inside_model=p.inside_model,  in_contact=p.in_contact))

            lastPoint = p

        #remove non-cutting points
#        cleanpath=[]
#        for p in newpath:
#            cutting = True
#            for cp in cleanpath:
#                if geometry.dist(p.position, cp.position) < min(radius, cp.dist_from_model):
#                    cutting = False
#            if cutting:
#                cleanpath.append(p)
        new_paths.append(GCode(newpath))
        self.outpaths=new_paths
        self.updateView()