import multiprocessing
import os
import threading
import time
from signal import SIGINT

multiprocessing.set_start_method("fork")  # noqa

import unittest
import pytest
from parameterized import parameterized
import shutil

import bilby
import numpy as np


_sampler_kwargs = dict(
    bilby_mcmc=dict(nsamples=200, printdt=1),
    cpnest=dict(nlive=100),
    dnest4=dict(
        max_num_levels=2,
        num_steps=10,
        new_level_interval=10,
        num_per_step=10,
        thread_steps=1,
        num_particles=50,
        max_pool=1,
    ),
    dynesty=dict(nlive=100),
    dynamic_dynesty=dict(
        nlive_init=100,
        nlive_batch=100,
        dlogz_init=1.0,
        maxbatch=0,
        maxcall=100,
        bound="single",
    ),
    emcee=dict(iterations=1000, nwalkers=10),
    kombine=dict(iterations=2000, nwalkers=20, autoburnin=False),
    nessai=dict(nlive=100, poolsize=1000, max_iteration=1000),
    nestle=dict(nlive=100),
    ptemcee=dict(
        nsamples=100,
        nwalkers=50,
        burn_in_act=1,
        ntemps=1,
        frac_threshold=0.5,
    ),
    PTMCMCsampler=dict(Niter=101, burn=2, isave=100),
    pymc3=dict(draws=50, tune=50, n_init=250),
    pymultinest=dict(nlive=100),
    pypolychord=dict(nlive=100),
    ultranest=dict(nlive=100, resume="overwrite", temporary_directory=False),
)


class TestRunningSamplers(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        bilby.core.utils.command_line_args.bilby_test_mode = False
        self.x = np.linspace(0, 1, 11)
        self.model = lambda x, m, c: m * x + c
        self.injection_parameters = dict(m=0.5, c=0.2)
        self.sigma = 0.1
        self.y = self.model(self.x, **self.injection_parameters) + np.random.normal(
            0, self.sigma, len(self.x)
        )
        self.likelihood = bilby.likelihood.GaussianLikelihood(
            self.x, self.y, self.model, self.sigma
        )

        self.priors = bilby.core.prior.PriorDict()
        self.priors["m"] = bilby.core.prior.Uniform(0, 5, boundary="periodic")
        self.priors["c"] = bilby.core.prior.Uniform(-2, 2, boundary="reflective")
        bilby.core.utils.check_directory_exists_and_if_not_mkdir("outdir")

    @staticmethod
    def conversion_function(parameters, likelihood, prior):
        converted = parameters.copy()
        if "derived" not in converted:
            converted["derived"] = converted["m"] * converted["c"]
        return converted

    def tearDown(self):
        del self.likelihood
        del self.priors
        bilby.core.utils.command_line_args.bilby_test_mode = False
        shutil.rmtree("outdir")

    @parameterized.expand(_sampler_kwargs.keys())
    def test_run_sampler_single(self, sampler):
        pytest.importorskip(sampler)
        self._run_sampler(sampler, pool_size=1)

    @parameterized.expand(_sampler_kwargs.keys())
    def test_run_sampler_pool(self, sampler):
        pytest.importorskip(sampler)
        self._run_sampler(sampler, pool_size=1)

    def _run_sampler(self, sampler, pool_size, **extra_kwargs):
        bilby.core.utils.check_directory_exists_and_if_not_mkdir("outdir")
        kwargs = _sampler_kwargs[sampler]
        kwargs["resume"] = kwargs.get("resume", False)
        res = bilby.run_sampler(
            likelihood=self.likelihood,
            priors=self.priors,
            sampler=sampler,
            save=True,
            npool=pool_size,
            conversion_function=self.conversion_function,
            **kwargs,
            **extra_kwargs,
        )
        assert "derived" in res.posterior
        assert res.log_likelihood_evaluations is not None

    @parameterized.expand(_sampler_kwargs.keys())
    def test_interrupt_sampler_single(self, sampler):
        pytest.importorskip(sampler)
        self._run_sampler(sampler, pool_size=1)

    @parameterized.expand(_sampler_kwargs.keys())
    def test_interrupt_sampler_pool(self, sampler):
        pytest.importorskip(sampler)
        self._run_sampler(sampler, pool_size=1)

    def _run_with_signal_handling(self, sampler, pool_size=1):
        pytest.importorskip(sampler)
        pid = os.getpid()

        def trigger_signal():
            # You could do something more robust, e.g. wait until port is listening
            time.sleep(1)
            os.kill(pid, SIGINT)

        thread = threading.Thread(target=trigger_signal)
        thread.daemon = True
        thread.start()

        try:
            self._run_sampler(sampler=sampler, pool_size=pool_size, checkpoint_exit_code=5)
        except SystemExit as error:
            self.assertEqual(error.code, 5)


if __name__ == "__main__":
    unittest.main()
