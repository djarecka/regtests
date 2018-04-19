"""Object to orchestrate worflow execution and output tests."""

import itertools
import json, csv
import os, shutil
import subprocess
import tempfile
import pdb
from collections import OrderedDict
from copy import deepcopy
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt, mpld3
import numpy as np

import container_generator as cg
import cwl_generator as cwlg


class WorkflowRegtest(object):
    def __init__(self, workflow_path, base_dir=None):
        if base_dir:
            self.base_dir = bas_dir
        else:
            self.base_dir = os.getcwd()
        self.workflow_path = workflow_path
        self.working_dir = os.path.join(self.base_dir, os.path.basename(self.workflow_path) + "_cwl")
        os.makedirs(self.working_dir, exist_ok=True)
        with open(os.path.join(self.workflow_path, "parameters.json")) as param_js:
            self.parameters = json.load(param_js, object_pairs_hook=OrderedDict)
        self.env_parameters = self.parameters["env"]
        self.script = os.path.join(self.workflow_path, "workflow",
                                   self.parameters["script"])
        self.command = self.parameters["command"] # TODO: adding arg
        self.tests = self.parameters["tests"] # should be a tuple (output_name, test_name)
        self.inputs = self.parameters["inputs"]
        self.tmpdir = tempfile.TemporaryDirectory(
            prefix="tmp-workflowregtest-", dir=os.getcwd()
        )
        self.docker_status = []

        self._create_matrix_of_envs()


    def _create_matrix_of_envs(self):
        """Create matrix of all combinations of environment variables.
            Create a list of short descriptions of envs as single strings"""
        params_as_strings = []
        for key, val in self.env_parameters.items():
            if isinstance(val, (list, tuple)):
                formatted = tuple("{}::{}".format(key, vv) for vv in val)
            else:
                formatted = tuple("{}::{}".format(key, val))
            params_as_strings.append(formatted)

        self.matrix_of_envs = list(itertools.product(*params_as_strings))

        self.soft_str = []
        for ii, specs in enumerate(self.matrix_of_envs):
            self.soft_str.append("_".join([string.split('::')[1].replace(':', '') for string in specs]))
            self.matrix_of_envs[ii] = [string.split('::') for string in specs]

        # creating additional a dictionary version
        self.matrix_envs_dict = [OrderedDict(mat) for mat in self.matrix_of_envs]



    def _testing_workflow(self):
        """Run workflow for all env combination, testing for all tests.
        Writing environmental parameters to report text file."""

        sha_list = [key for key in self.mapping]
        for ii, software_vers_str in enumerate(self.soft_str):
            #self.report_txt.write("\n * Environment:\n{}\n".format(software_vers))
            if self.docker_status[ii] == "docker ok":
                image = "repronim/regtests:{}".format(sha_list[ii])
                self._run_cwl(image, software_vers_str)


    def _generate_docker_image(self):
        """Generate all Dockerfiles"""
        self.mapping = cg.get_dict_of_neurodocker_dicts(self.matrix_of_envs)

        os.makedirs(os.path.join(self.workflow_path, 'json'), exist_ok=True) # TODO: self.workflow_path is temporary
        for sha1, neurodocker_dict in self.mapping.items():
            try:
                print("building images: {}".format(neurodocker_dict))
                cg.docker_main(self.workflow_path, neurodocker_dict, sha1)
                self.docker_status.append("docker ok")
            except Exception as e:
                self.docker_status.append("no docker")


    def _run_cwl(self, image, soft_ver_str):
        """Running workflow with CWL"""
        cwd = os.getcwd()
        working_dir_env = os.path.join(self.working_dir, soft_ver_str)
        os.makedirs(working_dir_env, exist_ok=True)
        os.chdir(working_dir_env)
        cwl_gen = cwlg.CwlGenerator(image, soft_ver_str, self.workflow_path, self.parameters)
        cwl_gen.create_cwl()
        subprocess.call(["cwl-runner", "--no-match-user", "cwl.cwl", "input.yml"])
        os.chdir(cwd)


    def run(self):
        """The main method that runs generate all docker files, build images
            and run a workflow in all environments.
        """
        self._generate_docker_image()
        self._testing_workflow()


    def merging_all_output(self):
        self.res_all = []
        no_docker = []
        ii_ok = None # just to have at least one env that docker was ok
        for ii, soft_d in enumerate(self.matrix_envs_dict):
            #self.res_all.append(deepcopy(soft_d))
            el_dict = deepcopy(soft_d)
            if self.docker_status[ii] == "docker ok":
                ii_ok = ii
                for (iir, test) in enumerate(self.tests):
                    file_name = os.path.join(self.working_dir, self.soft_str[ii],
                                             "report_{}.json".format(test["name"]))
                    with open(file_name) as f:
                        f_dict = json.load(f)
                        for key, res in f_dict.items():
                                el_dict["{}:{}".format(test["name"], key)] = res
            else:
                no_docker.append(ii)
            self.res_all.append(el_dict)

        self.res_keys = self.res_all[ii_ok].keys() - soft_d.keys()
        if ii_ok and no_docker:
            for ii in no_docker:
                for key in self.res_keys:
                    self.res_all[ii][key] = "N/A"

        keys_csv = self.res_all[0].keys()
        with open(os.path.join(self.working_dir, "output_all.csv"), 'w') as outfile:
            csv_writer = csv.DictWriter(outfile, keys_csv)
            csv_writer.writeheader()
            csv_writer.writerows(self.res_all)


    def plot_all_results_paralcoord(self):
        import pandas
        import plotly.graph_objs as go
        from plotly.offline import download_plotlyjs, init_notebook_mode, plot, iplot

        df = pandas.DataFrame(self.res_all)

        list_pl = []
        for i, k in self.env_parameters.items():
            soft_values = df[i]
            soft_values = soft_values.replace(k, list(range(len(k))))
            list_pl.append(dict(label=i, values=soft_values, tickvals=list(range(len(k))), ticktext=k ))

        for key in self.res_keys:
            if "reg" in key:
                reg_values = df[key]
                reg_values = reg_values.replace(["PASSED", "FAILED", "N/A"], [1, 0, 2])
                list_pl.append(dict(label=key, values=reg_values,
                                    tickvals=[0, 1, 2], ticktext=["failed", "passed", "N/A"]))
            else:
                stat_values = df[key]
                try:
                    stat_values = stat_values.replace(["N/A"], [-999])
                except TypeError:
                    pass
                list_pl.append(dict(label=key, values=stat_values))

        data = [go.Parcoords(line=dict(color = 'blue'), dimensions=list_pl)]

        layout = go.Layout(
            plot_bgcolor='#E5E5E5',
            paper_bgcolor='#E5E5E5'
        )

        fig = go.Figure(data=data, layout = layout)
        plot(fig, filename=os.path.join(self.working_dir,'parcoords_{}_All'.format(os.path.basename(self.workflow_path))))


    def dashboard_workflow(self):
        js_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples")
        for js_template in ["dashboard.js", "index.html", "style.css"]:
            shutil.copy2(os.path.join(js_dir, js_template), self.working_dir)
