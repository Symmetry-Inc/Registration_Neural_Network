import open3d as o3d
import click
from os.path import join, dirname, abspath
import numpy as np
import torch
import dcpcr.models.models as models
from dcpcr.utils.utils import extractPc

@click.command()
# Add your options here
@click.option('--checkpoint',
              '-ckpt',
              type=str,
              help='path to checkpoint file (.ckpt) to resume training.')
@click.option('--fine_tune',
              '-ft',
              type=bool,
              help='Whether to fine tune with icp or not.',
              default=True)


def main(checkpoint, fine_tune):
    cfg = torch.load(checkpoint)['hyper_parameters']
    cfg['checkpoint'] = checkpoint

    #data = np.load("/data/apollo-compressed/TrainData/ColumbiaPark/2018-10-03/submaps/019417.npy")
    source = o3d.io.read_point_cloud("./pcds/cloud_bin_0.pcd")
    target = o3d.io.read_point_cloud("./pcds/cloud_bin_1.pcd")
    # Downsample
    downpcd_source = source.voxel_down_sample(voxel_size=0.05)
    downpcd_target = target.voxel_down_sample(voxel_size=0.05)

    length = min(len(downpcd_target.points), len(downpcd_source.points))
    
    data_source, xyz_source, clr_source = extractPc(downpcd_source, length, normalize=True)
    data_target, xyz_target, clr_target = extractPc(downpcd_target, length, normalize=True)

    # Prepare result
    result = np.ones((length, 4))
    result[:,:3] = data_target[0,:,:3]

    # Visualize
    pcd_source = o3d.geometry.PointCloud()
    pcd_source.points = o3d.utility.Vector3dVector(xyz_source)
    pcd_source.colors = o3d.utility.Vector3dVector(clr_source)

    pcd_target = o3d.geometry.PointCloud()
    pcd_target.points = o3d.utility.Vector3dVector(xyz_target)
    pcd_target.colors = o3d.utility.Vector3dVector(clr_target)

    xyz_source  = torch.tensor(data_source, device=0).float()
    xyz_target  = torch.tensor(data_target, device=0).float()

    model = models.DCPCR.load_from_checkpoint(
        checkpoint).to(torch.device("cuda"))
    
    model.eval()
    est_pose, w, target_corr, weights = model(xyz_target, xyz_source)
    
    # transform
    est_pose = (est_pose.cpu()).detach().numpy()
    result = np.matmul(result, est_pose)
    print(est_pose)
    pcd_result = o3d.geometry.PointCloud()
    pcd_result.points = o3d.utility.Vector3dVector(result[0, :, :3])
    pcd_result.colors = o3d.utility.Vector3dVector(clr_target)
    #print(est_pose)
    o3d.visualization.draw_geometries([pcd_target, pcd_source, pcd_result])
if __name__ == "__main__":
    main()