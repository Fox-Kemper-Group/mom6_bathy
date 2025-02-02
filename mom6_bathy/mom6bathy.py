import os, sys
import numpy as np
import xarray as xr
from datetime import datetime
from midas.rectgrid_gen import supergrid
from scipy import interpolate

class mom6bathy(object):
    '''
    Bathymetry Generator for MOM6 grids (mom6grid).
    '''

    def __init__(self, grid, min_depth):
        '''
        MOM6 Simpler Models bathymetry constructor.

        Parameters
        ----------
        grid: mom6grid
            horizontal grid instance for which the bathymetry is to be created.
        min_depth: float
            Minimum water column depth. Columns with shallow depths are to be masked out.
        '''

        self._grid = grid
        self._depth = None
        self._min_depth = min_depth

    @property
    def depth(self):
        """
        MOM6 grid depth array. Positive below MSL.
        """
        return self._depth

    @property
    def min_depth(self):
        """
        Minimum water column depth. Columns with shallow depths are to be masked out.
        """
        return self._min_depth

    @property
    def max_depth(self):
        """
        Maximum water column depth.
        """
        return self.depth.max().item()

    @min_depth.setter
    def min_depth(self, new_min_depth):
        self._min_depth = new_min_depth

    @property
    def tmask(self):
        """
        Ocean domain mask at T grid. 1 if ocean, 0 if land.
        """
        tmask_da = xr.DataArray(
            np.where(self._depth>self._min_depth, 1, 0),
            dims = ['ny','nx'],
            attrs = {"name":"T mask"}
        )
        return tmask_da

    def set_flat(self, D):
        """
        Create a flat bottom bathymetry with a given depth D.

        Parameters
        ----------
        D: float
            Bathymetric depth of the flat bottom to be generated.
        """
        self._depth = xr.DataArray(
            np.full((self._grid.ny, self._grid.nx), D),
            dims = ['ny','nx'],
        )

    def set_depth(self, depth):
        """
        Apply a custom bathymetry via a user-defined depth array.

        Parameters
        ----------
        depth: np.array
            2-D Array of ocean depth.
        """

        assert depth.shape == (self._grid.ny, self._grid.nx), "Incompatible depth array shape"
        self._depth = xr.DataArray(
            depth,
            dims = ['ny','nx'],
        )

    def set_depth_via_topog_file(self, topog_file_path):
        """
        Apply a bathymetry read from an existing topog file

        Parameters
        ----------
        topog_file_path: str
            absolute path to an existing MOM6 topog file
        """

        assert os.path.exists(topog_file_path), f"Cannot find topog file at {topog_file_path}."

        ds = xr.open_dataset(topog_file_path)

        # sanity checks
        assert 'depth' in ds, f"Cannot find the 'depth' field in topog file {topog_file_path}"
        assert ds.depth.shape == (self._grid.ny, self._grid.nx), \
            f"Incompatible depth array shape in topog file {topog_file_path}"

        self.set_depth(ds.depth)


    def set_spoon(self, max_depth, dedge, rad_earth=6.378e6, expdecay=400000.0):
        '''
        Create a spoon-shaped bathymetry. Same effect as setting the TOPO_CONFIG parameter to "spoon".

        Parameters
        ----------
        max_depth : float
            Maximum depth of model in the units of D.
        dedge : float
            The depth [Z ~> m], at the basin edge
        rad_earth : float, optional
            Radius of earth
        expdecay : float, optional
            A decay scale of associated with the sloping boundaries [m]
        '''

        west_lon = self._grid.tlon[0,0]
        south_lat = self._grid.tlat[0,0]
        len_lon = self._grid.supergrid.dict['lenx']
        len_lat = self._grid.supergrid.dict['leny']
        self._depth = xr.DataArray(
            np.full((self._grid.ny, self._grid.nx), max_depth),
            dims = ['ny','nx'],
        )

        D0 = (max_depth - dedge) / \
                ((1.0 - np.exp(-0.5*len_lat*rad_earth*np.pi/(180.0*expdecay))) * \
                 (1.0 - np.exp(-0.5*len_lat*rad_earth*np.pi/(180.0*expdecay))))

        self._depth[:,:] = dedge + D0 * \
            ( np.sin(np.pi * (self._grid.tlon[:,:]-west_lon)/len_lon) * \
             (1.0 - np.exp((self._grid.tlat[:,:] - (south_lat+len_lat))*rad_earth*np.pi / \
                           (180.0*expdecay)) ))


    def set_bowl(self, max_depth, dedge, rad_earth=6.378e6, expdecay=400000.0):
        '''
        Create a bowl-shaped bathymetry. Same effect as setting the TOPO_CONFIG parameter to "bowl".

        Parameters
        ----------
        max_depth : float
            Maximum depth of model in the units of D.
        dedge : float
            The depth [Z ~> m], at the basin edge
        rad_earth : float, optional
            Radius of earth
        expdecay : float, optional
            A decay scale of associated with the sloping boundaries [m]
        '''

        west_lon = self._grid.tlon[0,0]
        south_lat = self._grid.tlat[0,0]
        len_lon = self._grid.supergrid.dict['lenx']
        len_lat = self._grid.supergrid.dict['leny']
        self._depth = xr.DataArray(
            np.full((self._grid.ny, self._grid.nx), max_depth),
            dims = ['ny','nx'],
        )

        D0 = (max_depth - dedge) / \
                ((1.0 - np.exp(-0.5*len_lat*rad_earth*np.pi/(180.0*expdecay))) * \
                 (1.0 - np.exp(-0.5*len_lat*rad_earth*np.pi/(180.0*expdecay))))

        self._depth[:,:] = dedge + D0 * \
            ( np.sin(np.pi * (self._grid.tlon[:,:]-west_lon)/len_lon) * \
             ((1.0 - np.exp(-(self._grid.tlat[:,:]-south_lat)*rad_earth*np.pi / \
                            (180.0*expdecay))) * \
             (1.0 - np.exp((self._grid.tlat[:,:]-(south_lat+len_lat)) * \
                            rad_earth*np.pi/(180.0*expdecay)))))



    def apply_ridge(self, height, width, lon, ilat):
        '''
        Apply a ridge to the bathymetry.

        Parameters
        ----------
        height : float
            Height of the ridge to be added.
        width : float
            Width of the ridge to be added.
        lon : float
            Longitude where the ridge is to be centered.
        ilat : pair of integers
            Initial and final latitude indices for the ridge.
        '''

        ridge_lon = [self._grid.tlon[0,0].data,
                     lon-width/2.,
                     lon,
                     lon+width/2.,
                     self._grid.tlon[0,-1].data]
        ridge_height = [0.,0.,-height,0.,0.]
        interp_func = interpolate.interp1d(ridge_lon, ridge_height, kind=2)
        ridge_height_mapped = interp_func(self._grid.tlon[0,:])
        ridge_height_mapped = np.where(ridge_height_mapped <= 0.0, ridge_height_mapped, 0.0)

        for j in range(ilat[0], ilat[1]):
            self._depth[j,:] +=  ridge_height_mapped

    def apply_land_frac(self, landfrac_filepath, landfrac_name, xcoord_name, ycoord_name, depth_fillval=0.0, cutoff_frac=0.5, method="bilinear"):
        '''
        Given a dataset containing land fraction, generate and apply ocean mask.

        Parameters
        ----------
        landfrac_filepath : str
            Path the netcdf file containing the land fraction field.
        landfrac_name : str
            The field name corresponding to the land fraction  (e.g., "landfrac").
        xcoord_name : str
            The name of the x coordinate of the landfrac dataset (e.g., "lon").
        ycoord_name : str
            The name of the y coordinate of the landfrac dataset (e.g., "lat").
        depth_fillval : float
            The depth value for dry cells.
        cutoff_frac : float
            Cells with landfrac > cutoff_frac are deemed land cells.
        method : str
            Mapping method for determining the ocean mask (lnd -> ocn)
        '''

        import xesmf as xe

        assert isinstance(landfrac_filepath, str), "landfrac_filepath must be a string"
        assert landfrac_filepath.endswith('.nc'), "landfrac_filepath must point to a netcdf file"
        ds = xr.open_dataset(landfrac_filepath)

        assert isinstance(landfrac_name, str), "landfrac_name must be a string"
        assert landfrac_name in ds, f"Couldn't find {landfrac_name} in {landfrac_filepath}"
        assert isinstance(xcoord_name, str), "xcoord_name must be a string"
        assert landfrac_name in ds, f"Couldn't find {xcoord_name} in {landfrac_filepath}"
        assert isinstance(ycoord_name, str), "ycoord_name must be a string"
        assert landfrac_name in ds, f"Couldn't find {ycoord_name} in {landfrac_filepath}"
        assert isinstance(depth_fillval, float), f"depth_fillval={depth_fillval} must be a float"
        assert depth_fillval<self._min_depth, f"depth_fillval (the depth of dry cells) must be smaller than the minimum depth {self._min_depth}"
        assert isinstance(cutoff_frac, float), f"cutoff_frac={cutoff_frac} must be a float"
        assert 0.0<=cutoff_frac<=1.0, f"cutoff_frac={cutoff_frac} must be 0<= and <=1"

        valid_methods = [
            'bilinear',
            'conservative',
            'conservative_normed',
            'patch',
            'nearest_s2d',
            'nearest_d2s']
        assert method in valid_methods, f"{method} is not a valid mapping method. Choose from: {valid_methods}"


        ds_mapped = xr.Dataset(
            data_vars = {},
            coords = {'lat':self._grid.tlat, 'lon':self._grid.tlon}
        )

        regridder = xe.Regridder(ds, ds_mapped, method, periodic=self._grid.supergrid.dict['cyclic_x'])
        mask_mapped = regridder(ds.landfrac)
        self._depth.data =  np.where(mask_mapped>cutoff_frac, depth_fillval, self._depth)

    def record_xml_changes(self):
        # Custom grid-specific XML changes:
        self._grid.append_to_sdb({
            'ocnice_xmlchanges' :{
                'OCN_DOMAIN_MESH': os.path.join(os.getcwd(), self.mesh_path),
                'ICE_DOMAIN_MESH': os.path.join(os.getcwd(), self.mesh_path), #warning: this assumes ocn and ice grids are the same. 
                'MASK_MESH': os.path.join(os.getcwd(), self.mesh_path), #warning: this assumes ocn and ice grids are the same. 
                'OCN_NX': self._grid.nx,
                'OCN_NY': self._grid.ny,
                'ICE_NX': self._grid.nx, #warning: this assumes ocn and ice grids are the same.
                'ICE_NY': self._grid.ny, #warning: this assumes ocn and ice grids are the same.
            }
        })

    def record_mom6_params(self):
        # Custom grid-specific MOM_input params:
        self._grid.append_to_sdb({
            'mom6_params' :{
                'INPUTDIR': './INPUT',
                'TRIPOLAR_N': self._grid.tripolar_n,
                'NIGLOBAL': self._grid.nx,
                'NJGLOBAL': self._grid.ny,
                'GRID_CONFIG': 'mosaic',
                'TOPO_CONFIG': '"file"',
                'MAXIMUM_DEPTH': str(self.max_depth),
                'MINIMUM_DEPTH': str(self.min_depth),
                'REENTRANT_X': self._grid.supergrid.dict['cyclic_x'],
                'REENTRANT_Y': self._grid.supergrid.dict['cyclic_y'],
                'DT': 1800.0,
                'NK': 20,
                'COORD_CONFIG': '"none"',
                'REGRIDDING_COORDINATE_MODE': '"Z*"',
                'ALE_COORDINATE_CONFIG': '"UNIFORM"',
                'TS_CONFIG': '"fit"',
                'T_REF': 5.0,
                'FIT_SALINITY': True,
            }
        })

    def record_cice_params(self, grid_file_path):
        # Custom grid-specific cice namelist params:
        self._grid.append_to_sdb({
            'cice_params' :{
                'grid_format' : 'nc',
                'grid_file' : os.path.join(os.getcwd(), grid_file_path),
                'kmt_file' : os.path.join(os.getcwd(), grid_file_path) # todo: correct this  
            }
        })

    def print_MOM6_runtime_params(self):

        print("{} = {}".format("INPUTDIR", '"./INPUT/"'))
        print("{} = {}".format("TRIPOLAR_N", self._grid.tripolar_n))
        print("{} = {}".format("NIGLOBAL", self._grid.nx))
        print("{} = {}".format("NJGLOBAL", self._grid.ny))
        print("{} = {}".format("GRID_CONFIG", '"mosaic"'))
        print("{} = {}".format("TOPO_CONFIG", '"file"'))
        print("{} = {}".format("MAXIMUM_DEPTH", str(self.max_depth)))
        print("{} = {}".format("MINIMUM_DEPTH", str(self.min_depth)))
        print("{} = {}".format("REENTRANT_X", self._grid.supergrid.dict['cyclic_x']))
        print("{} = {}".format("GRID_FILE", "???"))
        print("{} = {}".format("TOPO_FILE", "???"))



    def to_topog(self, file_path, title=None):
        '''
        Write the TOPO_FILE (bathymetry file) in netcdf format. The written file is
        to be read in by MOM6 during runtime.

        Parameters
        ----------
        file_path: str
            Path to TOPO_FILE to be written.
        title: str, optional
            File title.
        '''

        ds = xr.Dataset()

        # global attrs:
        ds.attrs['date_created'] = datetime.now().isoformat()
        if title:
            ds.attrs['title'] = title
        else:
            ds.attrs['title'] = "MOM6 topography file"

        ds['y'] = xr.DataArray(
            self._grid.tlat,
            dims = ['ny', 'nx'],
            attrs = {'long_name' : 'array of t-grid latitudes',
                     'units' : self._grid.tlat.units}
        )

        ds['x'] = xr.DataArray(
            self._grid.tlon,
            dims = ['ny', 'nx'],
            attrs = {'long_name' : 'array of t-grid longitutes',
                     'units' : self._grid.tlon.units}
        )

        ds['mask'] = xr.DataArray(
            self.tmask.astype(np.int32),
            dims = ['ny', 'nx'],
            attrs = {'long_name' : 'landsea mask at t points: 1 ocean, 0 land',
                     'units' : 'nondim'}
        )

        ds['depth'] = xr.DataArray(
            self._depth.data,
            dims = ['ny', 'nx'],
            attrs = {'long_name' : 't-grid cell depth',
                     'units' : "m"}
        )

        ds.to_netcdf(file_path)
        self._grid.append_to_sdb({'topog_path' : os.path.join(os.getcwd(), file_path)})


    def to_cice_grid(self, grid_file_path):

        assert 'degrees' in self._grid.tlat.units and 'degrees' in self._grid.tlon.units, "Unsupported coord"

        ds = xr.Dataset()

        # global attrs:
        ds.attrs['title'] = 'CICE grid file'

        ny = self._grid.ny
        nx = self._grid.nx


        ds['ulat'] = xr.DataArray(
            np.deg2rad(self._grid.qlat[1:,1:].data),
            dims = ['nj', 'ni'],
            attrs = {
                'long_name' : 'U grid center latitude',
                'units' : 'radians',
                'bounds' : 'latu_bounds',
            }
        )

        ds['ulon'] = xr.DataArray(
            np.deg2rad(self._grid.qlon[1:,1:].data),
            dims = ['nj', 'ni'],
            attrs = {
                'long_name' : 'U grid center longitude',
                'units' : 'radians',
                'bounds' : 'lonu_bounds',
            }
        )

        ds['tlat'] = xr.DataArray(
            np.deg2rad(self._grid.tlat.data),
            dims = ['nj', 'ni'],
            attrs = {
                'long_name' : 'T grid center latitude',
                'units' : 'degrees_north',
                'bounds' : 'latt_bounds',
            }
        )

        ds['tlon'] = xr.DataArray(
            np.deg2rad(self._grid.tlon.data),
            dims = ['nj', 'ni'],
            attrs = {
                'long_name' : 'T grid center longitude',
                'units' : 'degrees_east',
                'bounds' : 'lont_bounds',
            }
        )

        ds['htn'] = xr.DataArray(
            self._grid.dxCv.data * 100.0,
            dims = ['nj', 'ni'],
            attrs = {
                'long_name' : 'T cell width on North side',
                'units' : 'cm',
                'coordinates' : 'TLON TLAT',
            }
        )

        ds['hte'] = xr.DataArray(
            self._grid.dyCu.data * 100,
            dims = ['nj', 'ni'],
            attrs = {
                'long_name' : 'T cell width on East side',
                'units' : 'cm',
                'coordinates' : 'TLON TLAT',
            }
        )

        #ds['hus'] = xr.DataArray(
        #    self._grid.dxCu.data,
        #    dims = ['nj', 'ni'],
        #    attrs = {
        #        'long_name' : 'U cell width on South side',
        #        'units' : 'm',
        #        'coordinates' : 'ULON ULAT',
        #    }
        #)

        #ds['huw'] = xr.DataArray(
        #    self._grid.dyCv.data,
        #    dims = ['nj', 'ni'],
        #    attrs = {
        #        'long_name' : 'U cell width on West side',
        #        'units' : 'm',
        #        'coordinates' : 'ULON ULAT',
        #    }
        #)

        ds['angle'] = xr.DataArray(
            np.deg2rad(self._grid.angle.data), # todo: this is most likely wrong and will cause trouble with dipole/tripole grids.
            dims = ['nj', 'ni'],
            attrs = {
                'long_name' : 'angle grid makes with latitude line on U grid',
                'units' : 'radians',
                'coordinates' : 'ULON ULAT',
            }
        ) 


        ds['anglet'] = xr.DataArray(
            np.deg2rad(self._grid.angle.data), # todo: this is most likely wrong and will cause trouble with dipole/tripole grids.
            dims = ['nj', 'ni'],
            attrs = {
                'long_name' : 'angle grid makes with latitude line on T grid',
                'units' : 'radians',
                'coordinates' : 'TLON TLAT',
            }
        ) 

        ds['kmt'] = xr.DataArray(
            self.tmask.astype(np.float32),
            dims = ['nj', 'ni'],
            attrs = {'long_name' : 'mask of T grid cells',
                     'units' : 'unitless',
                     'coordinates' : 'TLON TLAT',
            }
        )

        ds.to_netcdf(grid_file_path)

        self.record_cice_params(grid_file_path)


    def to_SCRIP(self, SCRIP_path, title=None):
        '''
        Write the SCRIP grid file

        Parameters
        ----------
        SCRIP_path: str
            Path to SCRIP file to be written.
        title: str, optional
            File title.
        '''


        ds = xr.Dataset()

        # global attrs:
        ds.attrs['Conventions'] = "SCRIP"
        ds.attrs['date_created'] = datetime.now().isoformat()
        if title:
            ds.attrs['title'] = title

        ds['grid_dims'] = xr.DataArray(
            np.array([self._grid.ny, self._grid.nx]).astype(np.int32),
            dims = ['grid_rank']
        )
        ds['grid_center_lat'] = xr.DataArray(
            self._grid.tlat.data.flatten(),
            dims = ['grid_size'],
            attrs = {'units': self._grid.supergrid.dict['axis_units']}
        )
        ds['grid_center_lon'] = xr.DataArray(
            self._grid.tlon.data.flatten(),
            dims = ['grid_size'],
            attrs = {'units': self._grid.supergrid.dict['axis_units']}
        )
        ds['grid_imask'] = xr.DataArray(
            self.tmask.data.astype(np.int32).flatten(),
            dims = ['grid_size'],
            attrs = {'units': "unitless"}
        )

        ds['grid_corner_lat'] = xr.DataArray(
            np.zeros((ds.dims['grid_size'],4)),
            dims = ['grid_size', 'grid_corners'],
            attrs = {'units': self._grid.supergrid.dict['axis_units']}
        )
        ds['grid_corner_lon'] = xr.DataArray(
            np.zeros((ds.dims['grid_size'],4)),
            dims = ['grid_size', 'grid_corners'],
            attrs = {'units': self._grid.supergrid.dict['axis_units']}
        )
        for i in range(self._grid.nx):
            for j in range(self._grid.ny):
                k = (j*self._grid.nx+i)
                ds['grid_corner_lat'][k,0] = self._grid.qlat[j,i]
                ds['grid_corner_lat'][k,1] = self._grid.qlat[j,i+1]
                ds['grid_corner_lat'][k,2] = self._grid.qlat[j+1,i+1]
                ds['grid_corner_lat'][k,3] = self._grid.qlat[j+1,i]
                ds['grid_corner_lon'][k,0] = self._grid.qlon[j,i]
                ds['grid_corner_lon'][k,1] = self._grid.qlon[j,i+1]
                ds['grid_corner_lon'][k,2] = self._grid.qlon[j+1,i+1]
                ds['grid_corner_lon'][k,3] = self._grid.qlon[j+1,i]
        ds['grid_area'] = xr.DataArray(
            self._grid.tarea.data.flatten(),
            dims = ['grid_size']
        )

        ds.to_netcdf(SCRIP_path)

    def to_domain_file(self, domain_file_path):

        assert 'degrees' in self._grid.tlat.units and 'degrees' in self._grid.tlon.units, "Unsupported coord"

        ds = xr.Dataset()

        # global attrs:
        ds.attrs['title'] = 'CESM domain data'
        ds.attrs['Conventions'] = 'CF-1.0'
    
        ds['yc'] = xr.DataArray(
            self._grid.tlat,
            dims = ['nj', 'ni'],
            attrs = {
                'long_name' : 'latitude of grid cell center',
                'units' : 'degrees_north',
                'bounds' : 'yv',
            }
        )

        ds['xc'] = xr.DataArray(
            self._grid.tlon,
            dims = ['nj', 'ni'],
            attrs = {
                'long_name' : 'longitude of grid cell center',
                'units' : 'degrees_east',
                'bounds' : 'xv', 
            }
        )

        ds['yv'] = xr.DataArray(
            np.zeros((ds.dims['nj'],ds.dims['ni'],4)),
            dims = ['nj', 'ni', 'nv'],
            attrs = {
                'long_name' : 'latitude of grid cell vertices',
                'units' : 'degrees_north',
            }
        )

        ds['xv'] = xr.DataArray(
            np.zeros((ds.dims['nj'],ds.dims['ni'],4)),
            dims = ['nj', 'ni', 'nv'],
            attrs = {
                'long_name' : 'longitude of grid cell vertices',
                'units' : 'degrees_east',
            }
        )

        ds['yv'][:,:,0].data = self._grid.qlat[:-1,:-1].data 
        ds['yv'][:,:,1].data = self._grid.qlat[:-1, 1:].data 
        ds['yv'][:,:,2].data = self._grid.qlat[1: ,1: ].data 
        ds['yv'][:,:,3].data = self._grid.qlat[1: ,:-1].data 
        ds['xv'][:,:,0].data = self._grid.qlon[:-1,:-1].data 
        ds['xv'][:,:,1].data = self._grid.qlon[:-1,1: ].data 
        ds['xv'][:,:,2].data = self._grid.qlon[1: ,1: ].data 
        ds['xv'][:,:,3].data = self._grid.qlon[1: ,:-1].data 

        ds['mask'] = xr.DataArray(
            self.tmask.astype(np.int32),
            dims = ['nj', 'ni'],
            attrs = {'long_name' : 'domain mask',
                     'units' : 'unitless',
                     'coordinates' : 'xc yc',
                     'comment' : '0 value indicates cell is not active'}
        )

        ds['area'] = xr.DataArray(
            self._grid.tarea,
            dims = ['nj', 'ni'],
            attrs = {'long_name' : 'area of grid cell in radians squared',
                     'units' : 'radian2',
                     'coordinates' : 'xc yc'}
        )

        ds['frac'] = xr.DataArray(
            self.tmask.astype(np.float64),
            dims = ['nj', 'ni'],
            attrs = {'long_name' : 'fraction of grid cell that is active',
                     'units' : 'unitless',
                     'coordinates' : 'xc yc',
                     'filter1' : 'error if frac> 1.0+eps or frac < 0.0-eps; eps = 0.1000000E-11',
                     'filter2' : 'limit frac to [fminval,fmaxval]; fminval= 0.1000000E-02 fmaxval=  1.000000'}
        )

        ds.to_netcdf(domain_file_path)

    def to_ESMF_mesh(self, mesh_path, title=None):
        '''
        Write the ESMF mesh file

        Parameters
        ----------
        mesh_path: str
            Path to ESMF mesh file to be written.
        title: str, optional
            File title.
        '''

        ds = xr.Dataset()

        # global attrs:
        ds.attrs['gridType'] = "unstructured mesh"
        ds.attrs['date_created'] = datetime.now().isoformat()
        if title:
            ds.attrs['title'] = title


        tlon_flat = self._grid.tlon.data.flatten()
        tlat_flat = self._grid.tlat.data.flatten()
        ncells = len(tlon_flat) # i.e., elementCount in ESMF mesh nomenclature

        coord_units = self._grid.supergrid.dict['axis_units']

        ds['centerCoords'] = xr.DataArray(
            [ [tlon_flat[i], tlat_flat[i]] for i in range(ncells)],
            dims = ['elementCount', 'coordDim'],
            attrs = {'units': coord_units}
        )

        ds['numElementConn'] = xr.DataArray(
            np.full(ncells, 4).astype(np.int8),
            dims = ['elementCount'],
            attrs = {'long_name':'Node indices that define the element connectivity'}
        )

        ds['elementArea'] = xr.DataArray(
            self._grid.tarea.data.flatten(),
            dims = ['elementCount'],
            attrs = {'units': self._grid.tarea.units}
        )

        ds['elementMask'] = xr.DataArray(
            self.tmask.data.astype(np.int32).flatten(),
            dims = ['elementCount']
        )

        i0 = 1 # start index for node id's

        if self._grid.supergrid.dict['cyclic_x'] == False:

            qlon_flat = self._grid.qlon.data.flatten()
            qlat_flat = self._grid.qlat.data.flatten()
            nnodes = len(qlon_flat)
            nx = self._grid.nx
            ny = self._grid.ny
            assert nnodes == (nx+1) * (ny+1)

            ds['nodeCoords'] = xr.DataArray(
                [ [qlon_flat[i], qlat_flat[i]] for i in range(nnodes)],
                dims = ['nodeCount', 'coordDim'],
                attrs = {'units': coord_units}
            )

            # Below returns element connectivity of i-th element (assuming 0 based node and element indexing)
            get_element_conn = lambda i: [
                i0 + i%nx + (i//nx)*(nx+1),
                i0 + i%nx + (i//nx)*(nx+1) + 1,
                i0 + i%nx + (i//nx+1)*(nx+1) + 1,
                i0 + i%nx + (i//nx+1)*(nx+1)
            ]

        else: # cyclic x

            qlon_flat = self._grid.qlon.data[:,:-1].flatten()
            qlat_flat = self._grid.qlat.data[:,:-1].flatten()
            nnodes = len(qlon_flat)
            nx = self._grid.nx
            ny = self._grid.ny
            assert nnodes == nx * (ny+1)

            ds['nodeCoords'] = xr.DataArray(
                [ [qlon_flat[i], qlat_flat[i]] for i in range(nnodes)],
                dims = ['nodeCount', 'coordDim'],
                attrs = {'units': coord_units}
            )

            # Below returns element connectivity of i-th element (assuming 0 based node and element indexing)
            get_element_conn = lambda i: [
                i0 + i%nx + (i//nx)*(nx),
                i0 + i%nx + (i//nx)*(nx) + 1 - ( ((i+1)%nx)==0 )*nx,
                i0 + i%nx + (i//nx+1)*(nx) + 1 - ( ((i+1)%nx)==0 )*nx,
                i0 + i%nx + (i//nx+1)*(nx)
            ]

        ds['elementConn'] = xr.DataArray(
            np.array([get_element_conn(i) for i in range(ncells)]).astype(np.int32),
            dims = ['elementCount', 'maxNodePElement'],
            attrs = {'long_name': "Node indices that define the element connectivity",
                     'start_index': np.int32(i0)}
        )

        self.mesh_path = mesh_path
        ds.to_netcdf(self.mesh_path)
        self._grid.append_to_sdb({'mesh_path' : os.path.join(os.getcwd(), self.mesh_path)})
        self.record_xml_changes()
        self.record_mom6_params()

