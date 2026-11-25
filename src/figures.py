"""English figures generated directly from the supplied geometry and results."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch, Patch
from matplotlib.path import Path as PlotPath
import numpy as np
from .results import METRICS
from .sensitivity import compare_conditions, PROTOTYPES

ROOT = Path(__file__).resolve().parents[1]
LABELS = {'horizontal':'H', 'vertical':'V', 'hybrid':'HY', 'north_south':'NS'}
COLORS = {'CONDITIONED_VIRTUAL':'#6f9eaa','ENCLOSED_UNCONDITIONED':'#d0d3d7',
          'OUTDOOR_ROOF_CORRIDOR_OR_VOID':'#ffffff'}


def save(fig, out, name):
    for suffix in ['png','svg']:
        fig.savefig(out/f'{name}.{suffix}',dpi=180,bbox_inches='tight',facecolor='white')
    plt.close(fig)


def polygon_patch(rings, color):
    vertices, codes = [], []
    for ring in rings:
        vertices.extend(ring)
        codes.extend([PlotPath.MOVETO]+[PlotPath.LINETO]*(len(ring)-2)+[PlotPath.CLOSEPOLY])
    return PathPatch(PlotPath(vertices,codes),facecolor=color,edgecolor='#52616a',linewidth=.6)


def geometry_figure(out):
    geo = json.loads((ROOT/'data/geometry/gridded_footprints.geojson').read_text(encoding='utf-8'))
    fig, axes = plt.subplots(4,4,figsize=(9,8.4))
    all_xy = []
    for f in geo['features']:
        polys = [f['geometry']['coordinates']] if f['geometry']['type']=='Polygon' else f['geometry']['coordinates']
        all_xy.extend(xy for poly in polys for ring in poly for xy in ring)
    limits = np.array(all_xy)
    x0,y0 = limits.min(axis=0)-5
    x1,y1 = limits.max(axis=0)+5
    for i,level in enumerate(('B1','F1','F2','F3')):
        for j,prototype in enumerate(PROTOTYPES):
            ax = axes[i,j]
            features = [f for f in geo['features'] if f['properties']['prototype_id']==prototype and f['properties']['level']==level]
            # Draw outdoor categories first, then the actual closed zones.
            features.sort(key=lambda f:f['properties']['category']!='OUTDOOR_ROOF_CORRIDOR_OR_VOID')
            for f in features:
                polys = [f['geometry']['coordinates']] if f['geometry']['type']=='Polygon' else f['geometry']['coordinates']
                for poly in polys:
                    ax.add_patch(polygon_patch(poly,COLORS[f['properties']['category']]))
            ax.set(xlim=(x0,x1),ylim=(y0,y1),aspect='equal',xticks=[],yticks=[])
            for spine in ax.spines.values():
                spine.set_visible(False)
            if i==0:
                ax.set_title(LABELS[prototype]+' / '+prototype.replace('_',' ').title(),fontsize=10,pad=12)
            if j==0:
                ax.set_ylabel(level,rotation=0,labelpad=18,fontweight='bold')
    axes[3,3].plot([x1-25,x1-5],[y0+2,y0+2],color='#222',linewidth=2)
    axes[3,3].text(x1-15,y0+6,'20 m',ha='center',fontsize=8)
    axes[0,3].annotate('N',xy=(x1-6,y1-3),xytext=(x1-6,y1-22),ha='center',fontsize=8,
                       arrowprops={'arrowstyle':'->','color':'#333'})
    fig.suptitle('Four drawing-derived geometry scenarios',y=.99,fontsize=14)
    labels = ['Virtual conditioned zone','Enclosed, unconditioned','Outdoor / void']
    fig.legend([Patch(facecolor=c,edgecolor='#52616a') for c in COLORS.values()],labels,
               loc='lower center',ncol=3,frameon=False,fontsize=9,bbox_to_anchor=(.5,.01))
    fig.subplots_adjust(left=.06,right=.99,top=.92,bottom=.07,wspace=.1,hspace=.08)
    save(fig,out,'geometry')


def make_figures(rows, out: Path):
    out.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
                         'axes.spines.right':False,'svg.fonttype':'none'})
    geometry_figure(out)
    baseline = {r['prototype']:r for r in rows if r['group']=='baseline'}
    summary, _ = compare_conditions(rows)
    fig, (left,right) = plt.subplots(1,2,figsize=(11,4),layout='constrained',gridspec_kw={'width_ratios':[1.25,1]})
    x = np.arange(4)
    heat = [baseline[p][METRICS[0]] for p in PROTOTYPES]
    cool = [baseline[p][METRICS[1]] for p in PROTOTYPES]
    left.bar(x,heat,color='#bf6d49',label='Heating',width=.62)
    left.bar(x,cool,bottom=heat,color='#527f9c',label='Cooling',width=.62)
    for i,p in enumerate(PROTOTYPES):
        left.text(i,heat[i]+cool[i]+1,f'{heat[i]+cool[i]:.2f}',ha='center',fontsize=10)
    left.set(xticks=x,xticklabels=[LABELS[p] for p in PROTOTYPES],ylim=(0,90),
             ylabel='Annual ideal thermal demand (kWh/m²)',title='Baseline: shared virtual-use assumptions')
    left.legend(frameon=False,ncol=2,loc='upper right',fontsize=9)
    left.set_axisbelow(True)
    left.grid(axis='y',alpha=.15)
    for offset, group, color, label in [(-.18,'ofat','#869299','Single factor (16 conditions)'),(.18,'factorial','#386b70','Compound (24 conditions)')]:
        values = [summary[group]['metrics'][m]['conditions_with_reversal'] for m in METRICS]
        right.bar(np.arange(3)+offset,values,width=.34,color=color,label=label)
        for i,v in enumerate(values):
            right.text(i+offset,v+.4,str(v),ha='center',fontsize=10)
    right.set(xticks=np.arange(3),xticklabels=['Heating','Cooling','Combined'],ylim=(0,26),
              ylabel='Conditions with at least one pairwise reversal',title='Sensitivity of the comparison order')
    right.set_yticks([0,4,8,12,16,20,24])
    right.legend(frameon=False,loc='upper left',fontsize=8)
    right.grid(axis='y',alpha=.15)
    right.set_axisbelow(True)
    save(fig,out,'energy-sensitivity')

    conditions = sorted({r['condition'] for r in rows if r['group']=='factorial'})
    lookup = {(r['condition'],r['prototype']):r for r in rows if r['group']=='factorial'}
    fig, axes = plt.subplots(1,2,figsize=(9,8),layout='constrained')
    for ax,metric,title in zip(axes,[METRICS[1],METRICS[2]],['Cooling: change from baseline','Combined: change from baseline']):
        matrix = np.array([[lookup[c,p][metric]-baseline[p][metric] for p in PROTOTYPES] for c in conditions])
        limit = np.max(np.abs(matrix))
        im = ax.imshow(matrix,cmap='RdBu_r',vmin=-limit,vmax=limit,aspect='auto')
        ax.set(xticks=np.arange(4),xticklabels=[LABELS[p] for p in PROTOTYPES],
               yticks=np.arange(len(conditions)),yticklabels=conditions,title=title)
        ax.tick_params(axis='y',labelsize=8)
        fig.colorbar(im,ax=ax,shrink=.6,label='kWh/m²/year')
    save(fig,out,'compound-changes')
