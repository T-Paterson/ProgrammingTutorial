from jinja2 import Environment, FileSystemLoader

import json
import pathlib
import subprocess
import os
from itertools import takewhile
from datetime import datetime
from distutils.dir_util import copy_tree

import socketserver
import http.server

# Information available in page templates:
#	page_title
#	date
#	author
#	site_title
#	chapter_title
#	chapter_link
#	prev_title
#	next_title
#	prev_link
#	next_link
#	content

# Information available in index template:

# Information available in chapter template:
#	page_title
#	site_title
#	prev_title
#	next_title
#	prev_link
#	next_link
#	page_list (list of page objects)
#	content

# Information available in overall index template:
#	site_title
#	page_title
#	content
#	page_list (list of page objects)

class Page():
	def __init__(self, location, group):
		self.location = location
		self.group = group

		self.is_group = False

	def from_line(line, group):
		location = group.location / (line + ".md")
		return Page(location, group)

	def run_pandoc(self):
		in_path = str(self.location)
		out_path_obj = pathlib.Path("./docs", *self.location.parts[1:])
		self.final_path = out_path_obj.with_suffix(self.location.suffix.replace(".md", ""))

		subprocess.call(["pandoc",
			in_path,
			"--highlight-style", "pygments",
			"-f", "markdown", "-t", "html",
			"-o", str(self.final_path)])

	def load_meta(self):
		markdown = self.location.read_text()
		meta_lines = takewhile(lambda l: not l.startswith("---"), markdown.splitlines()[1:])
		meta_dict =  dict([(l.split(": ")[0], ": ".join(l.split(": ")[1:])) for l in meta_lines])
		self.title = meta_dict["Title"]
		self.author = meta_dict["Author"]
		self.date = datetime.strptime(meta_dict["Date"], "%Y-%m-%d")

	def apply_template(self, env):
		template = env.get_template("page.html")

		next_ = self.get_next()
		prev = self.get_prev()

		rendered = template.render(page_title = self.title,
			date = self.date,
			author = self.author,
			site_title = conf["title"],
			chapter_title = self.group.title,
			chapter_link = self.group.get_link_path(),
			next_title = next_.title if next_ is not None else None,
			next_link = next_.get_link_path() if next_ is not None else None,
			prev_title = prev.title if prev is not None else None,
			prev_link = prev.get_link_path() if prev is not None else None,
			content = self.final_path.read_text(),
			path_prefix = conf["path_prefix"])

		self.final_path.write_text(rendered)

	def get_next(self):
		in_group_loc = self.group.pages.index(self)

		if in_group_loc + 1 < len(self.group.pages):
			return self.group.pages[in_group_loc + 1]

		else:
			if self.group.group == None or self.group.group.pages.index(self.group) + 1 == len(self.group.group.pages):
				return None

			else:
				group_loc = self.group.group.pages.index(self.group)
				return self.group.group.pages[group_loc + 1]
	
	def get_prev(self):
		# If in a group and there is a predecessor within the same group,
		# If the predecessor is a group,
		# return the last page of that group unless the group is empty at which point return the group.
		# If the predecessor is a page,
		# return the page
		# If there is no predecessor in the group,
		# find the predecessor to the group in the parent. Return that group's last page.

		in_group_loc = self.group.pages.index(self)

		if in_group_loc > 0:
			if type(self.group.pages[in_group_loc - 1]) == Page:
				return self.group.pages[in_group_loc - 1]
			else:
				prev_group = self.group.pages[in_group_loc - 1]
				return prev_group if prev_group.pages == [] else prev_group.pages[-1]

		elif in_group_loc == 0:
			return self.group

		else:
			if self.group.group == None or self.group.group.pages.index(self.group) == 0:
				return None

			else:
				group_loc = self.group.group.pages.index(self.group)
				prev_group = self.group.group.pages[group_loc - 1]
				return prev_group if type(prev_group) == Page or prev_group.pages == [] else prev_group.pages[-1]

	def get_link_path(self):
		return "/" + str(pathlib.Path(*self.location.parts[1:]).with_suffix(self.location.suffix.replace(".md", "")))

class PageGroup():
	def __init__(self, location, group=None):
		self.location = location
		self.pages = []
		self.group = group

		self.is_group = True
	def from_lines(self, line_list):

		n = 0
		while n < len(line_list):
			line = line_list[n]

			if line_list[n].endswith(":"):
				inner_location = self.location / line[:-1]

				trimmed_lines = []

				while n + 1 < len(line_list) and line_list[n + 1].startswith("\t"):
					n += 1
					trimmed_lines.append(line_list[n][1:])

				inner_group = PageGroup(inner_location, group=self)
				inner_group.from_lines(trimmed_lines)

				self.pages.append(inner_group)

			else:
				page = Page.from_line(line.strip(), self)
				self.pages.append(page)

			n += 1

	def load_meta(self):
		markdown = (self.location / "index.html.md").read_text()
		meta_lines = takewhile(lambda l: not l.startswith("---"), markdown.splitlines()[1:])
		meta_dict = dict([(l.split(": ")[0], ": ".join(l.split(": ")[1:])) for l in meta_lines])
		self.title = meta_dict["Title"]
		self.author = meta_dict["Author"]
		self.date = datetime.strptime(meta_dict["Date"], "%Y-%m-%d")

		for p in self.pages:
			p.load_meta()

	def make_output_dirs(self):
		if self.group == None:
			pass

		else:
			parts = self.location.parts
			pathlib.Path( "./docs", *parts[1:]).mkdir(exist_ok=True)

		for page_or_group in self.pages:
			if type(page_or_group) == PageGroup:
				page_or_group.make_output_dirs()

	def run_pandoc(self):
		for p in self.pages:
			p.run_pandoc()

		in_path = str(self.location / "index.html.md")
		self.final_path = pathlib.Path("./docs", *self.location.parts[1:]) / "index.html"

		subprocess.call(["pandoc",
			in_path,
			"--highlight-style", "pygments",
			"-f", "markdown", "-t", "html",
			"-o", str(self.final_path)])

	def apply_template(self, env):
		for p in self.pages:
			p.apply_template(env)

		if self.group is not None:
			template = env.get_template("section.html")

			next_ = self.get_next()
			prev = self.get_prev()


			rendered = template.render(page_title = self.title,
				site_title = conf["title"],
				next_title = next_.title if next_ is not None else None,
				next_link = next_.get_link_path() if next_ is not None else None,
				prev_title = prev.title if prev is not None else None,
				prev_link = prev.get_link_path() if prev is not None else None,
				content = self.final_path.read_text(),
				page_list = self.pages,
				path_prefix = conf["path_prefix"])

			self.final_path.write_text(rendered)

		else:
			template = env.get_template("index.html")

			rendered = template.render(page_title = self.title,
				site_title = conf["title"],
				content = self.final_path.read_text(),
				page_list = self.pages,
				path_prefix = conf["path_prefix"])

			self.final_path.write_text(rendered)

	def get_prev(self):
		if self.group is None:
			return None

		else:
			in_group_index = self.group.pages.index(self)
			if in_group_index == 0:
				return None
			else:
				prev = self.group.pages[in_group_index - 1]
				if type(prev) == PageGroup:
					return prev if prev.pages == [] else prev.pages[-1]

				return prev

	def get_next(self):
		if self.group is None:
			return None

		else:
			in_group_index = self.group.pages.index(self)

			if self.pages != []:
				return self.pages[0]

			if in_group_index + 1 == len(self.group.pages):
				return None

			else:
				return self.group.pages[in_group_index + 1]

	def get_link_path(self):
		path = "/" + str(pathlib.Path(*self.location.parts[1:])) + "/"
		if path == "/./":
			path = "/"
		return path



if __name__ == "__main__":
	print("Simple Static Site Generator running...")
	
	print("Reading configuration...")

	with open("site.json") as conf_file:
		conf = json.load(conf_file)

	print("Setting up template engine...")
	template_env = Environment(loader=FileSystemLoader("Templates/"))

	print("Building site \"{}\"...".format(conf["title"]))

	print("Reading page tree...")
	top_group = PageGroup(pathlib.Path("./Pages"))
	top_group.from_lines(pathlib.Path("index.tree").read_text().splitlines())

	print("Loading page metadata...")
	top_group.load_meta()

	print("Making output directories...")
	top_group.make_output_dirs()

	print("Running PanDoc...")
	top_group.run_pandoc()

	print("Applying templates...")
	top_group.apply_template(template_env)

	print("Copying static files...")
	copy_tree("./static", "./docs/static")

	print("ALL DONE. Starting test server...")

	# os.chdir("./Build")
	# handler = http.server.SimpleHTTPRequestHandler
	# with socketserver.TCPServer(("", 8000), handler) as httpd:
	# 	print("Serving HTTP on port 8000.")
	# 	httpd.serve_forever()