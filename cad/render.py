import sys, numpy as np, trimesh, cadquery as cq
import vtk
from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray
import nod_case as n

def tm(shape, tol=0.03):
    v, f = shape.val().tessellate(tol, 0.2)
    return trimesh.Trimesh([[p.x, p.y, p.z] for p in v], f)

def actor(mesh, color, opacity=1.0):
    pts = vtk.vtkPoints(); pts.SetData(numpy_to_vtk(np.asarray(mesh.vertices, float), deep=True))
    faces = np.hstack([np.full((len(mesh.faces),1),3), mesh.faces]).astype(np.int64).ravel()
    cells = vtk.vtkCellArray(); cells.SetCells(len(mesh.faces), numpy_to_vtkIdTypeArray(faces, deep=True))
    pd = vtk.vtkPolyData(); pd.SetPoints(pts); pd.SetPolys(cells)
    nm = vtk.vtkPolyDataNormals(); nm.SetInputData(pd); nm.SetFeatureAngle(35); nm.Update()
    m = vtk.vtkPolyDataMapper(); m.SetInputConnection(nm.GetOutputPort())
    a = vtk.vtkActor(); a.SetMapper(m); a.GetProperty().SetColor(*color); a.GetProperty().SetOpacity(opacity)
    a.GetProperty().SetSpecular(0.25); a.GetProperty().SetSpecularPower(20)
    return a

def render(actors, cam_pos, focal, up, out, size=(900, 1100), parallel=None):
    r = vtk.vtkRenderer(); r.SetBackground(0.914, 0.902, 0.875)
    for a in actors: r.AddActor(a)
    w = vtk.vtkRenderWindow(); w.SetOffScreenRendering(1); w.AddRenderer(r); w.SetSize(*size)
    c = r.GetActiveCamera(); c.SetPosition(*cam_pos); c.SetFocalPoint(*focal); c.SetViewUp(*up)
    if parallel: c.ParallelProjectionOn(); c.SetParallelScale(parallel)
    r.ResetCameraClippingRange()
    w.Render()
    g = vtk.vtkWindowToImageFilter(); g.SetInput(w); g.Update()
    wr = vtk.vtkPNGWriter(); wr.SetFileName(out); wr.SetInputConnection(g.GetOutputPort()); wr.Write()

shell, lid, cap = n.make_shell(), n.make_lid(), n.make_keycap()
dark, lidc, capc = (0.16,0.165,0.18), (0.28,0.29,0.31), (0.85,0.47,0.34)
S, L, C = tm(shell), tm(lid), tm(cap)
# 1 front three-quarter, assembled
render([actor(S,dark), actor(L,lidc), actor(C,capc)], (90,10,110), (0,38,-12), (0,1,0), "render_front.png")
# 2 back three-quarter, lid removed, with internal parts as ghosts
b = n.box
ghost = [
 (b(-11,11, n.MOD_Y1-38.5, n.MOD_Y1, -6, -2), (0.2,0.35,0.55)),
 (b(-9.8,9.8, n.BAT_Y0, n.BAT_Y0+36, -15.6, -10.4), (0.75,0.76,0.78)),
 (b(-8.9,8.9, n.XIAO_Y0, n.XIAO_Y0+21, n.xiao_bot_z, n.xiao_bot_z+1.2), (0.15,0.45,0.3)),
 (b(5.7,12.7, n.CONN_CY-10.5, n.CONN_CY+10.5, -23.8, -16.8), (0.79,0.64,0.15)),
 (b(-12.7,-5.7, n.CONN_CY-10.5, n.CONN_CY+10.5, -23.8, -16.8), (0.79,0.64,0.15)),
]
acts = [actor(S,dark)] + [actor(tm(g),c) for g,c in ghost]
render(acts, (-70,-20,-90), (0,38,-12), (0,1,0), "render_back_open.png")
# 3 section through the key centre (cut at x=0)
half = shell.intersect(b(-30,0,-1,80,-30,2))
render([actor(tm(half),dark), actor(tm(cap.intersect(b(-30,0,-1,80,-30,2))),capc), actor(tm(lid.intersect(b(-30,0,-1,80,-30,2))),lidc)],
       (120,38,-12), (0,38,-12), (0,1,0), "render_section.png", parallel=42)
# 4 keycap underside
render([actor(C,capc)], (25,-10,-45), (0,n.KEY_CY,-2), (0,1,0), "render_keycap.png", size=(800,700))
# 5 lid inside
render([actor(L,lidc)], (40,-20,40), (0,38,-24), (0,1,0), "render_lid.png", size=(800,1000))
print("ok")
