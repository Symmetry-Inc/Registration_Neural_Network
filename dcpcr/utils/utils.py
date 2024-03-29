import os
import torch
import numpy as np
import pandas as pd
from scipy.spatial.transform import Rotation
import open3d as o3d

CONFIG_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '../config/'))
DATA_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '../data/'))
EXPERIMENT_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '../experiments/'))


def dict2object(dict_):
    assert isinstance(dict_,dict)
    class_ = eval(dict_['class'])
    init_params = class_.__init__.__code__.co_varnames
    # print(f'init vars: \n {init_params}')
    params = {k: dict_[k] for k in dict_ if k in init_params}
    # print(params)
    return class_(**params)


def insideRandBB(pts, scale, xy_translation: list):
    translation = xy_translation + [0.]
    p = np.ones([pts.shape[0], 3])
    p[:, :2] = pts[:, :2]
    rot = Rotation.from_euler(
        'z', np.random.rand()*90, degrees=True).as_matrix()

    bb = np.array([
        [0, -1., 1],
        [0, 1, 1],
        [1, 0, 1],
        [-1, 0, 1]
    ]).T
    bb[-1, :] = bb[-1, :]*scale
    bb = rot@bb
    t = (np.random.rand(3)*2-1)*np.array(translation)
    inside = (p-t)@bb
    inside = np.all(inside > 0, axis=-1, keepdims=True)
    return inside


def makeHomogeneous(p):
    shape = list(p.shape)
    shape[-1] = 1
    ps_t = torch.cat([p[..., :, :3], torch.ones(
        shape, device=p.device, dtype=p.dtype)], -1)
    return ps_t


def nanstd(t: torch.Tensor, dim):
    m = torch.nanmean(t, dim, keepdim=True)
    tc = (t - m)**2

    tc[torch.isnan(t)] = 0
    w = (~torch.isnan(t)).sum(dim)-1
    v = tc.sum(dim)/w
    return v.sqrt()


def pad(array, n_points=2000, pad=True, shuffle = False):
    """ array [n x m] -> [n_points x m],
        output:
            array [*,n_points x m], padded with zeros
            mask [*,n_points x 1], 1 if valid, 0 if not valid 
    """
    if shuffle:
        sample_idx = np.random.choice(array.shape[-2], n_points, replace=False)
        array = array[...,sample_idx,:]
    if not pad:
        return array, np.ones(array.shape[:-1]+(1,), dtype='bool')
    if len(array.shape) == 2:
        size = list(array.shape)
        size[-2] = n_points
        out = np.zeros(size, dtype='float32')
        l = min(n_points, array.shape[-2])
        out[:l, :] = array[:l, :]

        size[-1] = 1
        mask = np.zeros(size, dtype='bool')
        mask[:l, :] = 1
        return out, mask
    else:
        size = list(array.shape)
        size[-2] = n_points
        out = np.zeros(size, dtype='float32')
        l = min(n_points, array.shape[-2])
        out[..., :l, :] = array[..., :l, :]
        size[-1] = 1
        mask = np.zeros(size, dtype='bool')
        mask[..., :l, :] = 1
        return out, mask


def torch2o3d(pcd, colors=None, estimate_normals=False):
    pcd = pcd.detach().cpu().squeeze().numpy() if isinstance(pcd, torch.Tensor) else pcd
    
    assert len(pcd.shape) <= 2, "Batching not implemented"
    colors = colors.detach().cpu().squeeze().numpy() if isinstance(
        colors, torch.Tensor) else colors
    pcl = o3d.geometry.PointCloud()
    pcl.points = o3d.utility.Vector3dVector(pcd[:,:3])
    if estimate_normals:
        pcl.estimate_normals()
    if colors is not None:
        pcl.colors = o3d.utility.Vector3dVector(colors)
    return pcl

def normalizePc(points):
    if points.size != 0:    
        centroid = np.mean(points, axis=0)
        points -= centroid
        furthest_distance = np.max(np.sqrt(np.sum(abs(points)**2,axis=-1)))
        points /= furthest_distance
    return points

def extractPc(pcd, normalize=False):
    # Extract the xyzrgb points from pcd
    xyz = np.asarray(pcd.points)
    clr = np.asarray(pcd.colors)
    length = len(pcd.points)
    # Normalize
    if normalize:
        xyz = normalizePc(xyz)
    # Extract normalized values and store within np array
    data = np.zeros((1,length, 6))
    data[0,:,:3] = xyz[:length,:]
    data[0,:,3:6] = clr[:length,:]
    return data, xyz, clr

def transform(points, T, device):
    shape = list(points.shape)
    shape[-1] = 1
    ps_t = torch.cat([points[..., :, :3], torch.ones(shape, device=device)], -1)
    ps_t = (T@ps_t.transpose(-1, -2)).transpose(-1, -2)
    ps_t = ps_t[0, :, :3]
    return ps_t

def scaledLas(las_file):
    # Extract coordinates
    x_dimension = las_file.X
    y_dimension = las_file.Y
    z_dimension = las_file.Z
    # Extract scaling factors
    x_scale = las_file.header.scales[0]
    y_scale = las_file.header.scales[1]
    z_scale = las_file.header.scales[2]
    # Extract offsets
    x_offset = las_file.header.offsets[0]
    y_offset = las_file.header.offsets[1]
    z_offset = las_file.header.offsets[2]
    # Scale pcd
    las_file.X = (x_dimension * x_scale) + x_offset
    las_file.Y = (y_dimension * y_scale) + y_offset
    las_file.Z = (z_dimension * z_scale) + z_offset
    return x_scale

def storeCsv(building_id, predictions, ground_truth, file_name):
    df = pd.DataFrame({
    'Building ID':   building_id,
    'Prediction': predictions,
    'Ground truth': ground_truth})

    # Create a Pandas Excel writer using XlsxWriter as the engine.
    writer = pd.ExcelWriter(file_name, engine='xlsxwriter')

    # Write the dataframe data to XlsxWriter. Turn off the default header and
    # index and skip one row to allow us to insert a user defined header.
    df.to_excel(writer, sheet_name='Sheet1', startrow=1, header=False, index=False)

    # Get the xlsxwriter workbook and worksheet objects.
    workbook = writer.book
    worksheet = writer.sheets['Sheet1']

    # Get the dimensions of the dataframe.
    (max_row, max_col) = df.shape

    # Create a list of column headers, to use in add_table().
    column_settings = [{'header': column} for column in df.columns]

    # Add the Excel table structure. Pandas will add the data.
    worksheet.add_table(0, 0, max_row, max_col - 1, {'columns': column_settings})

    # Make the columns wider for clarity.
    worksheet.set_column(0, max_col - 1, 12)
    # Close the Pandas Excel writer and output the Excel file.
    writer.close()