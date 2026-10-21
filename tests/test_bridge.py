# -*- coding: utf-8 -*-
"""Offline regression tests (CPython 3). No CCX executable required."""
import io
import math
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'bridge'))
import bridge


class SectionTests(unittest.TestCase):
    def test_i_channel_and_angle_geometry(self):
        data = [
            ('I', dict(ia='157.5 mm', ib='152.9 mm',
                       ic='9.4 mm', id='6.6 mm'),
             'I', [0.1575,0.1529,0.0094,0.1529,0.0094,0.0066],
             0.00378994),
            ('C', dict(ca='70 mm', cb='180 mm', cc='11 mm', cd='8 mm'),
             'CHAN', [0.18,0.07,0.011,0.008], 0.002804),
            ('L', dict(la='70 mm', lb='70 mm', lc='8 mm'),
             'L', [0.07,0.07,0.008], 0.001056)]
        for shape, attrs, expected, dims, area in data:
            g = ET.Element('geometric', type=shape, **attrs)
            got = bridge.geom_ub31(g)
            self.assertEqual(got[0], expected)
            for x,y in zip(got[1],dims):
                self.assertAlmostEqual(x,y)
            self.assertAlmostEqual(got[2],area)

    def test_bad_flange_size_fails(self):
        g=ET.Element('geometric',type='I',ia='100 mm',ib='50 mm',
                     ic='60 mm',id='6 mm')
        with self.assertRaises(ValueError):
            bridge.geom_ub31(g)

    def test_v_axis_rotation(self):
        v=bridge.beam_v((0,0,0),(1,0,0),((0,0,1),math.pi/2.))
        for x,y in zip(v,(0,-1,0)):
            self.assertAlmostEqual(x,y,places=12)
        self.assertEqual(bridge.beam_v((0,0,0),(1,0,0),None),(0.,1.,0.))
        with self.assertRaises(ValueError):
            bridge.beam_v((0,0,0),(1,0,0),((1,0,0),0.))


def synthetic_liml(path):
    root=ET.Element('liml')
    ET.SubElement(root,'analysis',type='S30')
    ET.SubElement(root,'node',nid='1',x='0',y='0',z='0')
    ET.SubElement(root,'node',nid='2',x='1',y='0',z='0')
    ET.SubElement(root,'node',nid='3',x='1',y='1',z='0')
    group=ET.SubElement(root,'elset',name='beam',material='steel')
    ET.SubElement(group,'elem',eid='1',shape='line2',nodes='1 2')
    ET.SubElement(group,'elem',eid='2',shape='line2',nodes='2 3')
    material=ET.SubElement(root,'mat',name='steel')
    ET.SubElement(material,'geometric',type='I',ia='200 mm',ib='100 mm',
                  ic='10 mm',id='6 mm')
    ET.SubElement(material,'mechanical',type='Isotropic',
                  youngsmodulus='200 GPa',poissonratio='0.3')
    selected=ET.SubElement(root,'elementselection',name='rotated')
    ET.SubElement(selected,'element',eid='1')
    oriented=ET.SubElement(root,'orientation',selection='rotated')
    for k,v in [('vx','0'),('vy','0'),('vz','1'),('angleu','90 \u00b0')]:
        ET.SubElement(oriented,k).text=v
    ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)


class DeckTests(unittest.TestCase):
    def test_orientation_splits_section_sets_and_writes_cards(self):
        with tempfile.TemporaryDirectory() as td:
            source=os.path.join(td,'model.liml')
            target=os.path.join(td,'draft.inp')
            synthetic_liml(source)
            report=bridge.translate(source,target,'B31T',draft=True)
            self.assertEqual(report['nodes'],3)
            self.assertEqual(report['elements'],2)
            self.assertEqual(report['beam_section_orientation_groups'],2)
            self.assertFalse(report['safe_to_solve'])
            with io.open(target,'r',encoding='utf-8') as handle:
                text=handle.read()
            self.assertEqual(text.count('*BEAM SECTION,'),2)
            self.assertEqual(text.count('*ELEMENT,'),2)
            self.assertIn('SECTION=I',text)
            self.assertIn('0.2, 0.1, 0.01, 0.1, 0.01, 0.006',text)
            self.assertIn('0, -1,',text)
            self.assertIn('-1, 0, 0',text)
            self.assertIn('DO NOT SOLVE',text)


    def test_mecway_releases_and_global_offsets(self):
        with tempfile.TemporaryDirectory() as td:
            source=os.path.join(td,'model.liml')
            target=os.path.join(td,'draft.inp')

            root=ET.Element('liml')
            ET.SubElement(root,'analysis',type='S30')
            ET.SubElement(root,'node',nid='1',x='0',y='0',z='0')
            ET.SubElement(root,'node',nid='2',x='1',y='0',z='0')

            group=ET.SubElement(root,'elset',name='beam',material='steel')
            ET.SubElement(group,'elem',eid='1',shape='line2',nodes='1 2')

            material=ET.SubElement(root,'mat',name='steel')
            ET.SubElement(material,'geometric',type='I',ia='200 mm',
                          ib='100 mm',ic='10 mm',id='6 mm')
            ET.SubElement(material,'mechanical',type='Isotropic',
                          youngsmodulus='200 GPa',poissonratio='0.3')

            offset_sel=ET.SubElement(root,'elementselection',name='offset_beam')
            ET.SubElement(offset_sel,'element',eid='1')
            off=ET.SubElement(root,'offset',selection='offset_beam')
            ET.SubElement(off,'x').text='0 mm'
            ET.SubElement(off,'y').text='0 mm'
            ET.SubElement(off,'z').text='100 mm'

            face_sel=ET.SubElement(root,'faceselection',name='release_end')
            ET.SubElement(face_sel,'face',eid='1',faceid='3')
            joint=ET.SubElement(root,'flexiblejoint',selection='release_end')
            ET.SubElement(joint,'rotv')
            ET.SubElement(joint,'rotw')

            ET.ElementTree(root).write(
                source,encoding='utf-8',xml_declaration=True)

            report=bridge.translate(source,target,'B31T',draft=True)
            self.assertEqual(report['offset_elements'],1)
            self.assertEqual(report['released_element_ends'],1)

            with io.open(target,'r',encoding='utf-8') as handle:
                text=handle.read()

            # Beam along +X, default V=+Y, hence global +Z is local +W.
            self.assertIn('OFFSET1=(0,0,0.1), OFFSET2=(0,0,0.1)',text)
            # faceid=3 is element end 2; rotv+rotw = 16+32 = 48.
            self.assertIn('*USER BEAM RELEASE',text)
            self.assertIn('1, 2, 48',text)


if __name__=='__main__':
    unittest.main()
